"""Offline tests for the synchronous client.

Nothing here reaches the Permit REST API or a real PDP: every request is served
by a local ``pytest_httpserver`` instance and the API context is pre-populated,
so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import pytest
from pytest_httpserver import HTTPServer

from permit.api.context import ApiContext
from permit.api.sync_api_client import SyncPermitApiClient, SyncUsersApi
from permit.config import PermitConfig
from permit.enforcement.enforcer import SyncEnforcer
from permit.sync import Permit as SyncPermit
from permit.utils.sync import SYNC_WRAPPER_MARKER, SyncClass

ORG = "test-org"
PROJECT = "test-project"
ENVIRONMENT = "test-env"
FACTS = f"/v2/facts/{PROJECT}/{ENVIRONMENT}"


def offline_config(base_url: str, **overrides: Any) -> PermitConfig:
    """Build a PermitConfig whose context is already resolved to environment level."""
    api_context = ApiContext()
    api_context._save_api_key_accessible_scope(org=ORG, project=PROJECT, environment=ENVIRONMENT)
    api_context.set_environment_level_context(ORG, PROJECT, ENVIRONMENT)
    return PermitConfig(
        token="test-token",
        api_url=base_url,
        pdp=base_url,
        api_context=api_context,
        **overrides,
    )


@pytest.fixture
def config(httpserver: HTTPServer) -> PermitConfig:
    return offline_config(httpserver.url_for("").rstrip("/"))


def sync_wrapper_depth(func: Callable) -> int:
    """Count how many ``async_to_sync`` wrappers a callable is nested in."""
    depth = 0
    seen = set()
    while func is not None and id(func) not in seen:
        seen.add(id(func))
        if getattr(func, SYNC_WRAPPER_MARKER, False):
            depth += 1
        func = getattr(func, "__wrapped__", None)
    return depth


def user_payload(key: str) -> dict:
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


def test_async_method_is_wrapped_exactly_once():
    class Base(metaclass=SyncClass):
        async def fetch(self) -> str:
            return "fetched"

    assert sync_wrapper_depth(Base.fetch) == 1
    assert Base().fetch() == "fetched"


def test_subclass_does_not_rewrap_inherited_methods():
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


def test_genuinely_sync_method_is_left_untouched():
    class Mixed(metaclass=SyncClass):
        def ping(self) -> str:
            return "pong"

        async def fetch(self) -> str:
            return "fetched"

    assert sync_wrapper_depth(Mixed.ping) == 0
    assert not hasattr(Mixed.ping, "__wrapped__")
    assert Mixed().ping() == "pong"
    assert Mixed().fetch() == "fetched"


def test_method_wrapped_by_a_plain_decorator_is_still_converted():
    """A sync decorator that returns the inner coroutine (e.g. pydantic's
    ``validate_arguments``) must not hide the fact that the method is async."""

    def passthrough(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.__wrapped__ = func  # what functools.wraps records
        return wrapper

    class Decorated(metaclass=SyncClass):
        @passthrough
        async def fetch(self) -> str:
            return "fetched"

    assert sync_wrapper_depth(Decorated.fetch) == 1
    assert Decorated().fetch() == "fetched"


def test_real_sdk_classes_are_wrapped_exactly_once():
    assert sync_wrapper_depth(SyncPermitApiClient.get_user) == 1
    assert sync_wrapper_depth(SyncUsersApi.get) == 1
    assert sync_wrapper_depth(SyncEnforcer.check) == 1
    assert sync_wrapper_depth(SyncEnforcer.filter_objects) == 1


def test_every_public_method_of_the_api_client_is_synchronous():
    for name in dir(SyncPermitApiClient):
        if name.startswith("_"):
            continue
        attr = getattr(SyncPermitApiClient, name)
        if not callable(attr) or inspect.isclass(attr):
            continue
        assert not inspect.iscoroutinefunction(attr), f"{name} is still a coroutine function"
        assert sync_wrapper_depth(attr) == 1, f"{name} is wrapped {sync_wrapper_depth(attr)} times"


# --- the deprecated facade ------------------------------------------------


def test_deprecated_facade_get_user_issues_a_request(httpserver: HTTPServer, config: PermitConfig):
    payload = user_payload("user-1")
    httpserver.expect_oneshot_request(f"{FACTS}/users/user-1", method="GET").respond_with_json(payload)

    client = SyncPermitApiClient(config)
    with pytest.warns(DeprecationWarning):
        user = client.get_user("user-1")

    assert user.key == "user-1"
    httpserver.check_assertions()


def test_deprecated_facade_list_roles_issues_a_request(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_oneshot_request(f"/v2/schema/{PROJECT}/{ENVIRONMENT}/roles", method="GET").respond_with_json([])

    client = SyncPermitApiClient(config)
    with pytest.warns(DeprecationWarning):
        roles = client.list_roles()

    assert roles == []
    httpserver.check_assertions()


# --- the sync Permit facade ------------------------------------------------


def test_sync_permit_check(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_oneshot_request("/allowed", method="POST").respond_with_json({"allow": True})

    result = SyncPermit(config).check("user-1", "read", "document")

    assert result is True
    httpserver.check_assertions()


def test_sync_permit_authorized_users(httpserver: HTTPServer, config: PermitConfig):
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

    assert not inspect.iscoroutine(result)
    assert list(result.users) == ["user-1"]
    assert result.tenant == "default"
    httpserver.check_assertions()


def test_sync_permit_get_user_permissions(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_oneshot_request(
        "/user-permissions",
        method="POST",
        json={
            "user": {"key": "user-1"},
            "tenants": None,
            "resources": None,
            "resource_types": None,
        },
    ).respond_with_json({"default": {"tenant": {"key": "default"}, "permissions": ["document:read"]}})

    result = SyncPermit(config).get_user_permissions("user-1")

    assert not inspect.iscoroutine(result)
    assert result["default"]["permissions"] == ["document:read"]
    httpserver.check_assertions()


def test_sync_permit_filter_objects(httpserver: HTTPServer, config: PermitConfig):
    """``Enforcer.filter_objects`` awaits ``self.bulk_check``, which the sync
    client has already converted - the re-entrant call has to keep working."""
    httpserver.expect_oneshot_request("/allowed/bulk", method="POST").respond_with_json(
        {"allow": [{"allow": True}, {"allow": False}, {"allow": True}]}
    )

    resources = [
        {"type": "document", "key": "doc-1"},
        {"type": "document", "key": "doc-2"},
        {"type": "document", "key": "doc-3"},
    ]
    result = SyncPermit(config).filter_objects("user-1", "read", {}, resources)

    assert not inspect.iscoroutine(result)
    assert result == [resources[0], resources[2]]
    httpserver.check_assertions()


def test_sync_permit_bulk_check(httpserver: HTTPServer, config: PermitConfig):
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


def test_sync_permit_check_from_a_worker_thread(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})

    permit = SyncPermit(config)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in [executor.submit(permit.check, "u", "read", "document")] * 2]

    assert results == [True, True]
    httpserver.check_assertions()


def test_sync_permit_check_from_inside_a_running_event_loop(httpserver: HTTPServer, config: PermitConfig):
    """Calling the sync client from async code used to raise
    ``RuntimeError: This event loop is already running``."""
    httpserver.expect_oneshot_request("/allowed", method="POST").respond_with_json({"allow": True})

    permit = SyncPermit(config)

    async def main() -> bool:
        return permit.check("u", "read", "document")

    assert asyncio.run(main()) is True
    httpserver.check_assertions()


def test_sync_pdp_api_role_assignments_list(httpserver: HTTPServer, config: PermitConfig):
    """``RoleAssignmentsApi.list`` is decorated with pydantic's ``validate_arguments``,
    which hides the ``async def`` behind a plain function."""
    httpserver.expect_oneshot_request(
        "/local/role_assignments",
        method="GET",
        query_string={"page": "1", "per_page": "100", "user": "user-1"},
    ).respond_with_json([])

    result = SyncPermit(config).pdp_api.role_assignments.list(user_key="user-1")

    assert result == []
    httpserver.check_assertions()
