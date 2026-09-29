"""Offline tests for the synchronous client.

Nothing here reaches the Permit REST API or a real PDP: every request is served
by a local ``pytest_httpserver`` instance and the API context is pre-populated,
so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
import os
import runpy
import subprocess
import sys
import threading
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from pytest_httpserver import HTTPServer

import permit
from permit.api.sync_api_client import SyncPermitApiClient, SyncUsersApi
from permit.config import PermitConfig
from permit.enforcement.enforcer import SyncEnforcer
from permit.sync import Permit as SyncPermit
from permit.utils.deprecation import deprecated
from permit.utils.sync import SYNC_WRAPPER_MARKER, SyncClass, run_coroutine_sync
from tests.utils import FACTS, SCHEMA


def sync_wrapper_depth(func: Callable[..., object]) -> int:
    """Count how many ``async_to_sync`` wrappers a callable is nested in."""
    depth = 0
    seen: set[int] = set()
    candidate: object = func
    while candidate is not None and id(candidate) not in seen:
        seen.add(id(candidate))
        if getattr(candidate, SYNC_WRAPPER_MARKER, False):
            depth += 1
        candidate = getattr(candidate, "__wrapped__", None)
    return depth


def user_payload(key: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "key": key,
        "id": str(uuid4()),
        "organization_id": str(uuid4()),
        "project_id": str(uuid4()),
        "environment_id": str(uuid4()),
        "created_at": now,
        "updated_at": now,
        "email": f"{key}@example.com",
    }


# --- the metaclass itself -------------------------------------------------


def test_async_method_is_wrapped_exactly_once() -> None:
    class Base(metaclass=SyncClass):
        async def fetch(self) -> str:
            return "fetched"

    assert sync_wrapper_depth(Base.fetch) == 1
    assert Base().fetch() == "fetched"


def test_subclass_does_not_rewrap_inherited_methods() -> None:
    class Base(metaclass=SyncClass):
        async def fetch(self) -> str:
            return "fetched"

    class Child(Base):
        async def other(self) -> str:
            return "other"

    assert sync_wrapper_depth(Child.fetch) == 1
    assert sync_wrapper_depth(Child.other) == 1
    assert Child().fetch() == "fetched"
    assert Child().other() == "other"


def test_genuinely_sync_method_is_left_untouched() -> None:
    class Mixed(metaclass=SyncClass):
        def ping(self) -> str:
            return "pong"

        async def fetch(self) -> str:
            return "fetched"

    assert sync_wrapper_depth(Mixed.ping) == 0
    assert not hasattr(Mixed.ping, "__wrapped__")
    assert Mixed().ping() == "pong"
    assert Mixed().fetch() == "fetched"


def test_method_wrapped_by_a_plain_decorator_is_still_converted() -> None:
    """A sync decorator returning the inner coroutine must not hide that it is async.

    pydantic's ``validate_arguments`` is such a decorator.
    """

    def passthrough(func: Callable[..., object]) -> Callable[..., object]:
        def wrapper(*args: Any, **kwargs: Any) -> object:
            return func(*args, **kwargs)

        wrapper.__wrapped__ = func  # type: ignore[attr-defined] # what functools.wraps records
        return wrapper

    class Decorated(metaclass=SyncClass):
        @passthrough
        async def fetch(self) -> str:
            return "fetched"

    assert sync_wrapper_depth(Decorated.fetch) == 1
    assert Decorated().fetch() == "fetched"


def test_real_sdk_classes_are_wrapped_exactly_once() -> None:
    assert sync_wrapper_depth(SyncPermitApiClient.get_user) == 1
    assert sync_wrapper_depth(SyncUsersApi.get) == 1
    assert sync_wrapper_depth(SyncEnforcer.check) == 1
    assert sync_wrapper_depth(SyncEnforcer.filter_objects) == 1


def test_every_public_method_of_the_api_client_is_synchronous() -> None:
    for name in dir(SyncPermitApiClient):
        if name.startswith("_"):
            continue
        attr = getattr(SyncPermitApiClient, name)
        if not callable(attr) or inspect.isclass(attr):
            continue
        assert not inspect.iscoroutinefunction(attr), f"{name} is still a coroutine function"
        assert sync_wrapper_depth(attr) == 1, f"{name} is wrapped {sync_wrapper_depth(attr)} times"


# --- the deprecated facade ------------------------------------------------


def test_deprecated_facade_get_user_issues_a_request(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    payload = user_payload("user-1")
    httpserver.expect_oneshot_request(f"{FACTS}/users/user-1", method="GET").respond_with_json(
        payload
    )

    client = SyncPermitApiClient(config)
    with pytest.warns(DeprecationWarning, match=r"permit\.api\.users\.get\(\)"):
        user = client.get_user("user-1")

    assert user.key == "user-1"
    httpserver.check_assertions()


def test_deprecated_facade_list_roles_issues_a_request(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_oneshot_request(f"{SCHEMA}/roles", method="GET").respond_with_json([])

    client = SyncPermitApiClient(config)
    with pytest.warns(DeprecationWarning, match=r"permit\.api\.roles\.list\(\)"):
        roles = client.list_roles()

    assert roles == []
    httpserver.check_assertions()


# --- warnings from a blocking call's coroutine ------------------------------


def deprecation_sites(caught: list[warnings.WarningMessage]) -> list[tuple[str, int]]:
    return [(w.filename, w.lineno) for w in caught if issubclass(w.category, DeprecationWarning)]


def first_line_of(func: Callable[..., object]) -> tuple[str, int]:
    """The file and first body line of ``func``, where each helper below makes its call."""
    return func.__code__.co_filename, func.__code__.co_firstlineno + 1


def test_deprecated_facade_warns_at_a_call_made_inside_a_running_event_loop(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """With a loop already running, the call's coroutine runs in a worker thread of its own."""
    httpserver.expect_oneshot_request(f"{FACTS}/users/user-1", method="GET").respond_with_json(
        user_payload("user-1")
    )
    client = SyncPermitApiClient(config)

    async def main() -> None:
        client.get_user("user-1")

    with pytest.warns(DeprecationWarning, match=r"permit\.api\.get_user\(\)") as caught:
        asyncio.run(main())

    assert deprecation_sites(caught.list) == [first_line_of(main)]
    httpserver.check_assertions()


def test_concurrent_blocking_calls_each_warn_at_their_own_call() -> None:
    """A coroutine that runs for a blocking call warns at that call, not another thread's."""
    both_calls_running = threading.Barrier(2)

    class Api(metaclass=SyncClass):
        async def fetch(self) -> None:
            # Neither coroutine warns until both threads are inside their blocking call.
            await asyncio.to_thread(both_calls_running.wait, 10)
            await self.old_fetch()

        @deprecated("old_fetch() is deprecated")
        async def old_fetch(self) -> None:
            pass

    def first_caller() -> None:
        Api().fetch()

    def second_caller() -> None:
        Api().fetch()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(first_caller), executor.submit(second_caller)]
            for future in futures:
                future.result()

    assert sorted(deprecation_sites(caught)) == sorted(
        [first_line_of(first_caller), first_line_of(second_caller)]
    )


NO_CALLER_SCRIPT = """\
import atexit
import warnings

from permit.utils.deprecation import deprecated
from permit.utils.sync import SyncClass


class Api(metaclass=SyncClass):
    @deprecated("old_fetch() is deprecated")
    async def old_fetch(self) -> None:
        print("ran")


warnings.filterwarnings("always", message="old_fetch", category=DeprecationWarning)
# At exit, the interpreter calls the method from C, with no Python frame above it.
atexit.register(Api().old_fetch)
"""


def test_a_blocking_call_with_no_python_caller_warns_where_warnings_warn_would(
    tmp_path: Path,
) -> None:
    """C code can call a blocking method with no Python frame above it, as it calls an atexit hook.

    ``warnings.warn`` blames ``<sys>``, line 0, when it has no frame to blame, and so does the
    blocking call instead of failing.
    """
    script = tmp_path / "script.py"
    script.write_text(NO_CALLER_SCRIPT)
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("PYTHONWARNINGS", "PYTHONDEVMODE")
    }
    env["PYTHONPATH"] = str(Path(permit.__file__).resolve().parents[1])

    result = subprocess.run(
        [sys.executable, str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert (result.returncode, result.stdout) == (0, "ran\n"), result.stderr
    assert [line for line in result.stderr.splitlines() if "old_fetch" in line] == [
        "<sys>:0: DeprecationWarning: old_fetch() is deprecated"
    ]


def test_run_coroutine_sync_takes_just_the_coroutine() -> None:
    """run_coroutine_sync, public since 2.x, still works when called directly.

    It drives re-entrant awaits of converted methods, and a deprecated one warns at the line
    that called it.
    """

    class Api(metaclass=SyncClass):
        @deprecated("old_fetch() is deprecated")
        async def old_fetch(self) -> str:
            return "fetched"

    async def main() -> str:
        return await Api().old_fetch()

    def caller() -> str:
        return run_coroutine_sync(main())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert caller() == "fetched"

    assert deprecation_sites(caught) == [first_line_of(caller)]


def test_a_blocking_call_from_code_with_no_module_spec_warns_once(tmp_path: Path) -> None:
    """runpy.run_path() runs a file whose globals hold neither ``__spec__`` nor ``__loader__``."""

    class Api(metaclass=SyncClass):
        @deprecated("old_fetch() is deprecated")
        async def old_fetch(self) -> None:
            pass

    script = tmp_path / "script.py"
    script.write_text("api.old_fetch()\n")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        runpy.run_path(str(script), init_globals={"api": Api()})

    assert [(w.category, str(w.message), w.filename, w.lineno) for w in caught] == [
        (DeprecationWarning, "old_fetch() is deprecated", str(script), 1)
    ]


# --- the sync Permit facade ------------------------------------------------


def test_sync_permit_check(httpserver: HTTPServer, config: PermitConfig) -> None:
    httpserver.expect_oneshot_request("/allowed", method="POST").respond_with_json({"allow": True})

    result = SyncPermit(config).check("user-1", "read", "document")

    assert result is True
    httpserver.check_assertions()


def test_sync_permit_authorized_users(httpserver: HTTPServer, config: PermitConfig) -> None:
    httpserver.expect_oneshot_request("/authorized_users", method="POST").respond_with_json(
        {
            "resource": "document:*",
            "tenant": "default",
            "users": {
                "user-1": [
                    {
                        "user": "user-1",
                        "tenant": "default",
                        "resource": "document:*",
                        "role": "viewer",
                    }
                ]
            },
        }
    )

    result = SyncPermit(config).authorized_users("read", "document")

    # The blocking client is typed as blocking, so mypy rules a coroutine out already;
    # this checks the runtime value.
    assert not inspect.iscoroutine(cast("object", result))
    assert list(result.users) == ["user-1"]
    assert result.tenant == "default"
    httpserver.check_assertions()


def test_sync_permit_get_user_permissions(httpserver: HTTPServer, config: PermitConfig) -> None:
    httpserver.expect_oneshot_request(
        "/user-permissions",
        method="POST",
        json={
            "user": {"key": "user-1"},
            "tenants": None,
            "resources": None,
            "resource_types": None,
        },
    ).respond_with_json(
        {"default": {"tenant": {"key": "default"}, "permissions": ["document:read"]}}
    )

    result = SyncPermit(config).get_user_permissions("user-1")

    # The blocking client is typed as blocking, so mypy rules a coroutine out already;
    # this checks the runtime value.
    assert not inspect.iscoroutine(cast("object", result))
    assert result["default"]["permissions"] == ["document:read"]
    httpserver.check_assertions()


def test_sync_permit_filter_objects(httpserver: HTTPServer, config: PermitConfig) -> None:
    """The re-entrant call from ``filter_objects`` to ``bulk_check`` has to keep working.

    ``Enforcer.filter_objects`` awaits ``self.bulk_check``, which the sync client
    has already converted.
    """
    httpserver.expect_oneshot_request("/allowed/bulk", method="POST").respond_with_json(
        {"allow": [{"allow": True}, {"allow": False}, {"allow": True}]}
    )

    resources = [
        {"type": "document", "key": "doc-1"},
        {"type": "document", "key": "doc-2"},
        {"type": "document", "key": "doc-3"},
    ]
    result = SyncPermit(config).filter_objects("user-1", "read", {}, resources)

    # The blocking client is typed as blocking, so mypy rules a coroutine out already;
    # this checks the runtime value.
    assert not inspect.iscoroutine(cast("object", result))
    assert result == [resources[0], resources[2]]
    httpserver.check_assertions()


def test_sync_permit_bulk_check(httpserver: HTTPServer, config: PermitConfig) -> None:
    httpserver.expect_oneshot_request("/allowed/bulk", method="POST").respond_with_json(
        {"allow": [{"allow": True}, {"allow": False}]}
    )

    result = SyncPermit(config).bulk_check(
        [
            {"user": "user-1", "action": "read", "resource": "document"},
            {"user": "user-2", "action": "read", "resource": "document"},
        ]
    )

    assert result == [True, False]
    httpserver.check_assertions()


def test_sync_permit_check_from_a_worker_thread(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})

    permit = SyncPermit(config)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result()
            for future in [executor.submit(permit.check, "u", "read", "document")] * 2
        ]

    assert results == [True, True]
    httpserver.check_assertions()


def test_sync_permit_check_from_inside_a_running_event_loop(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """The sync client can be called from async code.

    It used to raise ``RuntimeError: This event loop is already running``.
    """
    httpserver.expect_oneshot_request("/allowed", method="POST").respond_with_json({"allow": True})

    permit = SyncPermit(config)

    async def main() -> bool:
        return permit.check("u", "read", "document")

    assert asyncio.run(main()) is True
    httpserver.check_assertions()


def test_sync_pdp_api_role_assignments_list(httpserver: HTTPServer, config: PermitConfig) -> None:
    """The PDP role assignments list works through the sync client.

    ``RoleAssignmentsApi.list`` is decorated with pydantic's ``validate_arguments``,
    which hides the ``async def`` behind a plain function.
    """
    httpserver.expect_oneshot_request(
        "/local/role_assignments",
        method="GET",
        query_string={"page": "1", "per_page": "100", "user": "user-1"},
    ).respond_with_json([])

    result = SyncPermit(config).pdp_api.role_assignments.list(user_key="user-1")

    assert result == []
    httpserver.check_assertions()
