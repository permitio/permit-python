"""Offline tests for the deprecated flat methods on ``permit.api`` (PER-16177).

Each deprecated method must warn that it is removed in permit 4.0, name its
replacement, point the warning at the line that called it, send the request that
replacement sends and return what it returns. Every request is served by a local
``pytest_httpserver`` and the API context is pre-populated, so no API key and no
``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import copy
import inspect
import json
import os
import subprocess
import sys
import warnings
from operator import attrgetter
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, Union

import pytest
from pytest_httpserver import HTTPServer

import permit
from permit import Permit
from permit.api.deprecated import DeprecatedApi
from permit.api.elements import UserLoginAsResponse
from permit.api.models import (
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    RoleAssignmentRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    TenantCreate,
    TenantRead,
    TenantUpdate,
    UserCreate,
    UserRead,
)
from permit.config import PermitConfig
from permit.sync import Permit as SyncPermit
from tests.utils import FACTS, SCHEMA, Call, call, sent

TIMESTAMP = "2024-01-01T00:00:00+00:00"
IDS = {
    "id": "00000000-0000-4000-8000-000000000001",
    "organization_id": "00000000-0000-4000-8000-000000000002",
    "project_id": "00000000-0000-4000-8000-000000000003",
    "environment_id": "00000000-0000-4000-8000-000000000004",
}


def user(key: str) -> Dict[str, Any]:
    return {**IDS, "key": key, "email": f"{key}@example.com", "created_at": TIMESTAMP, "updated_at": TIMESTAMP}


def role(key: str) -> Dict[str, Any]:
    return {**IDS, "key": key, "name": key.title(), "created_at": TIMESTAMP, "updated_at": TIMESTAMP}


def tenant(key: str) -> Dict[str, Any]:
    return {
        **IDS,
        "key": key,
        "name": key.title(),
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        "last_action_at": TIMESTAMP,
    }


def resource(key: str) -> Dict[str, Any]:
    return {**IDS, "key": key, "name": key.title(), "created_at": TIMESTAMP, "updated_at": TIMESTAMP}


def assignment() -> Dict[str, Any]:
    return {
        **IDS,
        "user": "user-1",
        "role": "admin",
        "tenant": "tenant-1",
        "user_id": "00000000-0000-4000-8000-000000000005",
        "role_id": "00000000-0000-4000-8000-000000000006",
        "tenant_id": "00000000-0000-4000-8000-000000000007",
        "created_at": TIMESTAMP,
    }


LOGIN = {"redirect_url": "https://app.example.com/login?token=abc", "token": "abc"}


class FacadeCase(NamedTuple):
    """One deprecated method, the replacement its warning names, and the request both send.

    The test resolves and calls ``replacement.path`` itself, so the warning cannot name
    a method other than the one the facade is compared with. ``response`` is the JSON
    the server answers with, or None for an empty 204; ``model`` is what it parses into.
    """

    facade: Call
    replacement: Call
    request: Tuple[str, str]
    response: Union[Dict[str, Any], List[Dict[str, Any]], None]
    model: Optional[type]


NEW_USER = {"key": "user-1", "email": "user-1@example.com"}
NEW_TENANT = {"key": "tenant-1", "name": "Tenant 1"}
TENANT_CHANGES = {"name": "Renamed", "description": None}
NEW_ROLE = {"key": "admin", "name": "Admin", "permissions": ["document:read"]}
ROLE_CHANGES = {"description": "Administrators"}
NEW_RESOURCE = {"key": "document", "name": "Document", "actions": {"read": {}}}
RESOURCE_CHANGES = {"name": "Doc"}
ASSIGNMENT = {"user": "user-1", "role": "admin", "tenant": "tenant-1"}

# The methods that take a model or a dict have one case with each.
CASES = [
    FacadeCase(
        facade=call("permit.api.get_user", "user-1"),
        replacement=call("permit.api.users.get", "user-1"),
        request=("GET", f"{FACTS}/users/user-1"),
        response=user("user-1"),
        model=UserRead,
    ),
    FacadeCase(
        facade=call("permit.api.get_role", "admin"),
        replacement=call("permit.api.roles.get", "admin"),
        request=("GET", f"{SCHEMA}/roles/admin"),
        response=role("admin"),
        model=RoleRead,
    ),
    FacadeCase(
        facade=call("permit.api.get_tenant", "tenant-1"),
        replacement=call("permit.api.tenants.get", "tenant-1"),
        request=("GET", f"{FACTS}/tenants/tenant-1"),
        response=tenant("tenant-1"),
        model=TenantRead,
    ),
    FacadeCase(
        facade=call("permit.api.get_assigned_roles", "user-1", "tenant-1", page=2, per_page=10),
        replacement=call("permit.api.users.get_assigned_roles", "user-1", tenant="tenant-1", page=2, per_page=10),
        request=("GET", f"{FACTS}/role_assignments"),
        response=[assignment()],
        model=RoleAssignmentRead,
    ),
    FacadeCase(
        facade=call("permit.api.get_resource", "document"),
        replacement=call("permit.api.resources.get", "document"),
        request=("GET", f"{SCHEMA}/resources/document"),
        response=resource("document"),
        model=ResourceRead,
    ),
    FacadeCase(
        facade=call("permit.api.list_roles", page=2, per_page=10),
        replacement=call("permit.api.roles.list", page=2, per_page=10),
        request=("GET", f"{SCHEMA}/roles"),
        response=[role("admin"), role("viewer")],
        model=RoleRead,
    ),
    FacadeCase(
        facade=call("permit.api.sync_user", NEW_USER),
        replacement=call("permit.api.users.sync", NEW_USER),
        request=("PUT", f"{FACTS}/users/user-1"),
        response=user("user-1"),
        model=UserRead,
    ),
    FacadeCase(
        facade=call("permit.api.sync_user", UserCreate(**NEW_USER)),
        replacement=call("permit.api.users.sync", UserCreate(**NEW_USER)),
        request=("PUT", f"{FACTS}/users/user-1"),
        response=user("user-1"),
        model=UserRead,
    ),
    FacadeCase(
        facade=call("permit.api.delete_user", "user-1"),
        replacement=call("permit.api.users.delete", "user-1"),
        request=("DELETE", f"{FACTS}/users/user-1"),
        response=None,
        model=None,
    ),
    FacadeCase(
        facade=call("permit.api.list_tenants", page=2, per_page=10),
        replacement=call("permit.api.tenants.list", page=2, per_page=10),
        request=("GET", f"{FACTS}/tenants"),
        response=[tenant("tenant-1")],
        model=TenantRead,
    ),
    FacadeCase(
        facade=call("permit.api.create_tenant", NEW_TENANT),
        replacement=call("permit.api.tenants.create", NEW_TENANT),
        request=("POST", f"{FACTS}/tenants"),
        response=tenant("tenant-1"),
        model=TenantRead,
    ),
    FacadeCase(
        facade=call("permit.api.create_tenant", TenantCreate(**NEW_TENANT)),
        replacement=call("permit.api.tenants.create", TenantCreate(**NEW_TENANT)),
        request=("POST", f"{FACTS}/tenants"),
        response=tenant("tenant-1"),
        model=TenantRead,
    ),
    FacadeCase(
        facade=call("permit.api.update_tenant", "tenant-1", TENANT_CHANGES),
        replacement=call("permit.api.tenants.update", "tenant-1", TENANT_CHANGES),
        request=("PATCH", f"{FACTS}/tenants/tenant-1"),
        response=tenant("tenant-1"),
        model=TenantRead,
    ),
    FacadeCase(
        facade=call("permit.api.update_tenant", "tenant-1", TenantUpdate(**TENANT_CHANGES)),
        replacement=call("permit.api.tenants.update", "tenant-1", TenantUpdate(**TENANT_CHANGES)),
        request=("PATCH", f"{FACTS}/tenants/tenant-1"),
        response=tenant("tenant-1"),
        model=TenantRead,
    ),
    FacadeCase(
        facade=call("permit.api.delete_tenant", "tenant-1"),
        replacement=call("permit.api.tenants.delete", "tenant-1"),
        request=("DELETE", f"{FACTS}/tenants/tenant-1"),
        response=None,
        model=None,
    ),
    FacadeCase(
        facade=call("permit.api.create_role", NEW_ROLE),
        replacement=call("permit.api.roles.create", NEW_ROLE),
        request=("POST", f"{SCHEMA}/roles"),
        response=role("admin"),
        model=RoleRead,
    ),
    FacadeCase(
        facade=call("permit.api.create_role", RoleCreate(**NEW_ROLE)),
        replacement=call("permit.api.roles.create", RoleCreate(**NEW_ROLE)),
        request=("POST", f"{SCHEMA}/roles"),
        response=role("admin"),
        model=RoleRead,
    ),
    FacadeCase(
        facade=call("permit.api.update_role", "admin", ROLE_CHANGES),
        replacement=call("permit.api.roles.update", "admin", ROLE_CHANGES),
        request=("PATCH", f"{SCHEMA}/roles/admin"),
        response=role("admin"),
        model=RoleRead,
    ),
    FacadeCase(
        facade=call("permit.api.update_role", "admin", RoleUpdate(**ROLE_CHANGES)),
        replacement=call("permit.api.roles.update", "admin", RoleUpdate(**ROLE_CHANGES)),
        request=("PATCH", f"{SCHEMA}/roles/admin"),
        response=role("admin"),
        model=RoleRead,
    ),
    FacadeCase(
        facade=call("permit.api.assign_role", "user-1", "admin", "tenant-1"),
        replacement=call("permit.api.users.assign_role", ASSIGNMENT),
        request=("POST", f"{FACTS}/users/user-1/roles"),
        response=assignment(),
        model=RoleAssignmentRead,
    ),
    FacadeCase(
        facade=call("permit.api.unassign_role", "user-1", "admin", "tenant-1"),
        replacement=call("permit.api.users.unassign_role", ASSIGNMENT),
        request=("DELETE", f"{FACTS}/users/user-1/roles"),
        response=None,
        model=None,
    ),
    FacadeCase(
        facade=call("permit.api.delete_role", "admin"),
        replacement=call("permit.api.roles.delete", "admin"),
        request=("DELETE", f"{SCHEMA}/roles/admin"),
        response=None,
        model=None,
    ),
    FacadeCase(
        facade=call("permit.api.create_resource", NEW_RESOURCE),
        replacement=call("permit.api.resources.create", NEW_RESOURCE),
        request=("POST", f"{SCHEMA}/resources"),
        response=resource("document"),
        model=ResourceRead,
    ),
    FacadeCase(
        facade=call("permit.api.create_resource", ResourceCreate(**NEW_RESOURCE)),
        replacement=call("permit.api.resources.create", ResourceCreate(**NEW_RESOURCE)),
        request=("POST", f"{SCHEMA}/resources"),
        response=resource("document"),
        model=ResourceRead,
    ),
    FacadeCase(
        facade=call("permit.api.update_resource", "document", RESOURCE_CHANGES),
        replacement=call("permit.api.resources.update", "document", RESOURCE_CHANGES),
        request=("PATCH", f"{SCHEMA}/resources/document"),
        response=resource("document"),
        model=ResourceRead,
    ),
    FacadeCase(
        facade=call("permit.api.update_resource", "document", ResourceUpdate(**RESOURCE_CHANGES)),
        replacement=call("permit.api.resources.update", "document", ResourceUpdate(**RESOURCE_CHANGES)),
        request=("PATCH", f"{SCHEMA}/resources/document"),
        response=resource("document"),
        model=ResourceRead,
    ),
    FacadeCase(
        facade=call("permit.api.delete_resource", "document"),
        replacement=call("permit.api.resources.delete", "document"),
        request=("DELETE", f"{SCHEMA}/resources/document"),
        response=None,
        model=None,
    ),
    FacadeCase(
        facade=call("permit.api.elements_login_as", "user-1", "tenant-1"),
        replacement=call("permit.elements.login_as", "user-1", "tenant-1"),
        request=("POST", "/v2/auth/elements_login_as"),
        response=LOGIN,
        model=UserLoginAsResponse,
    ),
]


def removal_warning(case: FacadeCase) -> str:
    return (
        f"{case.facade.path}() is deprecated and will be removed in permit 4.0; use {case.replacement.path}() instead."
    )


def deprecations(caught: List[warnings.WarningMessage]) -> List[Tuple[type, str, str, int]]:
    """Every DeprecationWarning in ``caught``, whoever raised it, and the line it points at.

    Other categories are left out: a ResourceWarning, for one, comes from garbage
    collection and can land in whichever test happens to be running.
    """
    return [
        (w.category, str(w.message), w.filename, w.lineno) for w in caught if issubclass(w.category, DeprecationWarning)
    ]


def call_blocking(method: Callable[..., Any], args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any:
    return method(*args, **kwargs)


async def call_awaiting(method: Callable[..., Any], args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any:
    return await method(*args, **kwargs)


# Where each client's deprecation warning must point: the line in this file that calls
# the method, which is the first line of the helper above that calls it for that client.
CALL_SITES = {
    "sync": (__file__, call_blocking.__code__.co_firstlineno + 1),
    "async": (__file__, call_awaiting.__code__.co_firstlineno + 1),
}


MODEL_INPUTS = (UserCreate, TenantCreate, TenantUpdate, RoleCreate, RoleUpdate, ResourceCreate, ResourceUpdate)


def case_id(case: FacadeCase) -> str:
    """The method's name, with "-model" on the case that passes a model instead of a dict."""
    name = case.facade.path.rpartition(".")[2]
    if any(isinstance(arg, MODEL_INPUTS) for arg in case.facade.args):
        return f"{name}-model"
    return name


def assert_parsed(result: Any, case: FacadeCase) -> None:
    if case.model is None:
        assert result is None
    elif isinstance(case.response, list):
        assert [type(item) for item in result] == [case.model] * len(case.response)
    else:
        assert type(result) is case.model


def test_the_table_covers_every_deprecated_method():
    deprecated = {
        f"permit.api.{name}" for name, value in vars(DeprecatedApi).items() if inspect.iscoroutinefunction(value)
    }

    assert deprecated == {case.facade.path for case in CASES}
    assert len(deprecated) == 21


@pytest.mark.parametrize("flavour", ["async", "sync"])
@pytest.mark.parametrize("case", CASES, ids=[case_id(case) for case in CASES])
def test_deprecated_method_warns_and_matches_its_replacement(
    httpserver: HTTPServer, config: PermitConfig, case: FacadeCase, flavour: str
):
    http_method, path = case.request
    handler = httpserver.expect_request(path, method=http_method)
    if case.response is None:
        handler.respond_with_data("", status=204)
    else:
        handler.respond_with_json(case.response)

    client = Permit(config) if flavour == "async" else SyncPermit(config)

    def invoke(target: Call) -> Any:
        # Each call gets its own copy of the inputs, so neither can see what the other did to them.
        args, kwargs = copy.deepcopy((target.args, target.kwargs))
        method = attrgetter(target.path.removeprefix("permit."))(client)
        if flavour == "async":
            return asyncio.run(call_awaiting(method, args, kwargs))
        result = call_blocking(method, args, kwargs)
        assert not inspect.isawaitable(result)
        return result

    with warnings.catch_warnings(record=True) as replacement_warnings:
        warnings.simplefilter("always")
        expected = invoke(case.replacement)
    with pytest.warns(DeprecationWarning) as facade_warnings:
        result = invoke(case.facade)

    assert deprecations(replacement_warnings) == []
    assert deprecations(facade_warnings) == [(DeprecationWarning, removal_warning(case), *CALL_SITES[flavour])]

    assert len(httpserver.log) == 2, [sent(request) for request, _ in httpserver.log]
    replacement_request, facade_request = (sent(request) for request, _ in httpserver.log)
    assert (facade_request["method"], facade_request["path"]) == case.request
    assert facade_request == replacement_request

    assert_parsed(result, case)
    assert result == expected


# The directories that hold the permit package this process imported and the tests
# package, so that the script imports the same copies whether or not permit is installed.
PERMIT_PARENT = Path(permit.__file__).resolve().parents[1]
TESTS_PARENT = Path(__file__).resolve().parents[1]

SCRIPT = """\
import asyncio
import json
import sys
import warnings

from permit import Permit
from permit.sync import Permit as SyncPermit
from tests.utils import offline_config

config = offline_config(sys.argv[1])


def call_blocking():
    SyncPermit(config).api.get_user("user-1")


async def call_awaiting():
    await Permit(config).api.get_user("user-1")


# Under the interpreter's warning filters, each call made three times from the same line.
for _ in range(3):
    call_blocking()
    asyncio.run(call_awaiting())

# With every warning recorded, whatever issued it.
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    call_blocking()
    asyncio.run(call_awaiting())
print(json.dumps([[w.category.__name__, str(w.message), w.filename, w.lineno] for w in caught]))
"""

SCRIPT_CALL_LINES = [
    SCRIPT.splitlines().index('    SyncPermit(config).api.get_user("user-1")') + 1,
    SCRIPT.splitlines().index('    await Permit(config).api.get_user("user-1")') + 1,
]


def test_a_script_gets_one_warning_per_call_at_the_call(httpserver: HTTPServer, tmp_path: Path):
    """A script runs as ``__main__``, which has no ``__spec__``, and it is the one module
    Python's default filters show DeprecationWarnings for.

    The script calls the method through each client, three times from the same line. The
    default filters (no ``-W`` option, PYTHONWARNINGS or dev mode) print a warning once per
    line that issues it, so each client's warning must be printed once, at its call. With
    every warning recorded, one call through each client must issue those two warnings and
    nothing else.
    """
    [case] = [case for case in CASES if case.facade.path == "permit.api.get_user"]
    http_method, path = case.request
    httpserver.expect_request(path, method=http_method).respond_with_json(case.response)
    script = tmp_path / "script.py"
    script.write_text(SCRIPT)
    env = {name: value for name, value in os.environ.items() if name not in ("PYTHONWARNINGS", "PYTHONDEVMODE")}
    env["PYTHONPATH"] = os.pathsep.join([str(PERMIT_PARENT), str(TESTS_PARENT)])

    result = subprocess.run(
        [sys.executable, str(script), httpserver.url_for("").rstrip("/")],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    message = removal_warning(case)
    assert [line for line in result.stderr.splitlines() if message in line] == [
        f"{script}:{line}: DeprecationWarning: {message}" for line in SCRIPT_CALL_LINES
    ]
    assert json.loads(result.stdout) == [
        ["DeprecationWarning", message, str(script), line] for line in SCRIPT_CALL_LINES
    ]
