"""Offline regression tests.

These tests never reach the Permit REST API, a PDP, or any other remote host and
they need no API key: every request is served by a local ``pytest_httpserver``
instance, and the SDK context is pre-populated so no API-key scope lookup is
issued.
"""

import inspect
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union, get_type_hints
from uuid import UUID, uuid4

import aiohttp
import pydantic
import pytest
from packaging.requirements import Requirement
from packaging.version import Version
from pydantic.v1 import ValidationError
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit, Resource, User
from permit.api.context import ApiKeyAccessLevel
from permit.api.elements import ElementsApi
from permit.api.models import RoleAssignmentCreate, RoleAssignmentRemove, UserCreate
from permit.api.resource_instances import ResourceInstancesApi
from permit.api.users import UsersApi
from permit.config import PermitConfig
from permit.enforcement.enforcer import CheckQuery
from permit.exceptions import (
    PermitApiError,
    PermitConnectionError,
    PermitContextError,
    PermitError,
    PermitException,
    handle_api_error,
)
from permit.pdp_api.pdp_api_client import SyncPDPApi
from permit.utils import pydantic_version
from permit.utils.context import ContextStore
from permit.utils.deprecation import deprecated
from tests.utils import FACTS


def role_assignment_read_payload() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "user": "user-1",
        "role": "admin",
        "tenant": "tenant-1",
        "user_id": str(uuid4()),
        "role_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "project_id": str(uuid4()),
        "environment_id": str(uuid4()),
        "created_at": now,
    }


def user_read_payload(key: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "key": key,
        "id": str(uuid4()),
        "organization_id": str(uuid4()),
        "project_id": str(uuid4()),
        "environment_id": str(uuid4()),
        "created_at": now,
        "updated_at": now,
    }


def single_request(httpserver: HTTPServer) -> Request:
    """Return the only request the server handled, failing if there was not exactly one."""
    assert len(httpserver.log) == 1, f"expected exactly one request, got {[r.url for r, _ in httpserver.log]}"
    return httpserver.log[0][0]


async def test_resource_instances_list_sends_detailed_filter_as_query_string(
    httpserver: HTTPServer, config: PermitConfig
):
    """detailed_key must reach the wire as a string: yarl rejects bool query values."""
    httpserver.expect_request(f"{FACTS}/resource_instances", method="GET").respond_with_json([])

    await ResourceInstancesApi(config).list(detailed_key=True)

    assert single_request(httpserver).args["detailed"] == "true"


async def test_resource_instances_list_sends_detailed_false_as_query_string(
    httpserver: HTTPServer, config: PermitConfig
):
    httpserver.expect_request(f"{FACTS}/resource_instances", method="GET").respond_with_json([])

    await ResourceInstancesApi(config).list(detailed_key=False)

    assert single_request(httpserver).args["detailed"] == "false"


async def test_resource_instances_list_omits_detailed_when_not_requested(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request(f"{FACTS}/resource_instances", method="GET").respond_with_json([])

    await ResourceInstancesApi(config).list()

    assert "detailed" not in single_request(httpserver).args


async def test_users_sync_does_not_mutate_the_caller_dict(httpserver: HTTPServer, config: PermitConfig):
    """The dict branch of users.sync() must not pop 'key' out of the caller's dict."""
    # an invalid email keeps pydantic's Union[UserCreate, dict] coercion on the dict branch
    user = {"key": "user-1", "email": "not-an-email"}
    httpserver.expect_request(f"{FACTS}/users/user-1", method="PUT").respond_with_json(user_read_payload("user-1"))

    await UsersApi(config).sync(user)

    assert user == {"key": "user-1", "email": "not-an-email"}


async def test_users_sync_dict_branch_is_reusable(httpserver: HTTPServer, config: PermitConfig):
    """A caller may retry with the same dict; the second call must not raise KeyError."""
    user = {"key": "user-1", "email": "not-an-email"}
    httpserver.expect_request(f"{FACTS}/users/user-1", method="PUT").respond_with_json(user_read_payload("user-1"))
    api = UsersApi(config)

    await api.sync(user)
    await api.sync(user)

    assert len(httpserver.log) == 2


async def test_users_assign_role_strips_unset_optional_fields(httpserver: HTTPServer, config: PermitConfig):
    """users.assign_role must match role_assignments.assign and not transmit explicit nulls."""
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="POST").respond_with_json(
        role_assignment_read_payload()
    )

    await UsersApi(config).assign_role(RoleAssignmentCreate(user="user-1", role="admin", tenant="tenant-1"))

    assert single_request(httpserver).get_json() == {"role": "admin", "tenant": "tenant-1"}


async def test_users_unassign_role_strips_unset_optional_fields(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="DELETE").respond_with_data("", status=204)

    await UsersApi(config).unassign_role(RoleAssignmentRemove(user="user-1", role="admin", tenant="tenant-1"))

    assert single_request(httpserver).get_json() == {"role": "admin", "tenant": "tenant-1"}


async def test_users_assign_role_sends_the_same_body_for_a_dict(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="POST").respond_with_json(
        role_assignment_read_payload()
    )

    await UsersApi(config).assign_role({"user": "user-1", "role": "admin", "tenant": "tenant-1"})

    assert single_request(httpserver).get_json() == {"role": "admin", "tenant": "tenant-1"}


async def test_users_unassign_role_sends_the_same_body_for_a_dict(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="DELETE").respond_with_data("", status=204)

    await UsersApi(config).unassign_role({"user": "user-1", "role": "admin", "tenant": "tenant-1"})

    assert single_request(httpserver).get_json() == {"role": "admin", "tenant": "tenant-1"}


def test_model_input_parameters_are_the_bare_model_at_runtime():
    # ModelInput and ModelListInput widen these annotations for type checkers only.
    # validate_arguments reads the runtime annotation and must still see the model.
    assert get_type_hints(UsersApi.create.raw_function)["user_data"] is UserCreate
    assert get_type_hints(UsersApi.bulk_create.raw_function)["users"] == List[UserCreate]
    # sync() passes an invalid dict through as it is, which a bare dict keeps doing.
    assert get_type_hints(UsersApi.sync.raw_function)["user"] == Union[UserCreate, dict]


def test_user_and_resource_aliases_work_with_isinstance():
    # Type checkers see Dict[str, Any] in these aliases. At runtime they keep the
    # bare dict, because isinstance rejects a parameterized one.
    assert isinstance({"key": "user-1"}, User)
    assert isinstance("user-1", User)
    assert isinstance({"type": "document"}, Resource)
    assert isinstance("document", Resource)


async def test_users_create_rejects_an_invalid_dict_before_sending_anything(
    httpserver: HTTPServer, config: PermitConfig
):
    with pytest.raises(ValidationError, match="email"):
        await UsersApi(config).create({"key": "user-1", "email": "not-an-email"})

    assert httpserver.log == []


async def test_users_create_validates_a_dict_into_the_model(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request(f"{FACTS}/users", method="POST").respond_with_json(user_read_payload("user-1"))

    await UsersApi(config).create({"key": "user-1", "email": "user@example.com"})

    assert single_request(httpserver).get_json() == {"key": "user-1", "email": "user@example.com"}


async def test_users_assign_role_keeps_explicitly_provided_resource_instance(
    httpserver: HTTPServer, config: PermitConfig
):
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="POST").respond_with_json(
        role_assignment_read_payload()
    )

    await UsersApi(config).assign_role(
        RoleAssignmentCreate(user="user-1", role="admin", tenant="tenant-1", resource_instance="doc:readme")
    )

    assert single_request(httpserver).get_json() == {
        "role": "admin",
        "tenant": "tenant-1",
        "resource_instance": "doc:readme",
    }


@pytest.mark.parametrize(
    ("permitted", "required"),
    [
        (ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY, ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY),
        (ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY, ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY),
        (ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY, ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY),
        (ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY, ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY),
        (ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY, ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY),
        (ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY, ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY),
    ],
)
async def test_ensure_access_level_accepts_a_key_broad_enough_for_the_endpoint(
    config: PermitConfig, permitted: ApiKeyAccessLevel, required: ApiKeyAccessLevel
):
    api = UsersApi(config)
    api.config.api_context._permitted_access_level = permitted

    await api._ensure_access_level(required)


@pytest.mark.parametrize(
    ("permitted", "required"),
    [
        (ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY, ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY),
        (ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY, ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY),
        (ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY, ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY),
    ],
)
async def test_ensure_access_level_rejects_a_key_too_narrow_for_the_endpoint(
    config: PermitConfig, permitted: ApiKeyAccessLevel, required: ApiKeyAccessLevel
):
    api = UsersApi(config)
    api.config.api_context._permitted_access_level = permitted

    with pytest.raises(PermitContextError):
        await api._ensure_access_level(required)


def test_sync_pdp_api_initializes_the_base_client_state(config: PermitConfig):
    """SyncPDPApi must run PermitPdpApiClient.__init__, not skip it."""
    client = SyncPDPApi(config)

    assert client._config is config
    assert client._base_url == config.pdp
    assert client._headers["Authorization"] == "Bearer test-token"
    assert client._headers["Content-Type"] == "application/json"


async def test_every_sdk_client_sends_the_standard_bearer_scheme(httpserver: HTTPServer, config: PermitConfig) -> None:
    """The enforcer, REST API client and PDP API client must all send "Bearer <token>"."""
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    httpserver.expect_request(f"{FACTS}/users", method="GET").respond_with_json(
        {"data": [], "total_count": 0, "page_count": 0}
    )
    httpserver.expect_request("/local/role_assignments", method="GET").respond_with_json([])
    permit = Permit(config)

    await permit.check("user-1", "read", "document")
    await permit.api.users.list()
    await permit.pdp_api.role_assignments.list()

    # Read the raw header from the log: expect_request(headers=...) matches the
    # Authorization scheme case-insensitively, so it would also accept "bearer".
    sent = {request.path: request.headers.get("Authorization") for request, _ in httpserver.log}
    assert sent == {
        "/allowed": "Bearer test-token",
        f"{FACTS}/users": "Bearer test-token",
        "/local/role_assignments": "Bearer test-token",
    }


async def test_elements_login_as_sends_canonical_uuid_strings(httpserver: HTTPServer, config: PermitConfig):
    """UUID ids must be sent in canonical hyphenated form, not UUID.hex."""
    httpserver.expect_request("/v2/auth/elements_login_as", method="POST").respond_with_json(
        {"redirect_url": "http://elements.permit.test/login"}
    )

    await ElementsApi(config).login_as(
        UUID("01234567-89ab-cdef-0123-456789abcdef"),
        UUID("fedcba98-7654-3210-fedc-ba9876543210"),
    )

    assert single_request(httpserver).get_json() == {
        "user_id": "01234567-89ab-cdef-0123-456789abcdef",
        "tenant_id": "fedcba98-7654-3210-fedc-ba9876543210",
    }


async def test_elements_login_as_passes_string_ids_through(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request("/v2/auth/elements_login_as", method="POST").respond_with_json(
        {"redirect_url": "http://elements.permit.test/login"}
    )

    await ElementsApi(config).login_as("user-1", "tenant-1")

    assert single_request(httpserver).get_json() == {"user_id": "user-1", "tenant_id": "tenant-1"}


def test_context_store_exposes_no_silently_ignored_transform_api():
    """register_transform()/transform() were dead: the enforcer never consulted them."""
    assert not hasattr(ContextStore, "register_transform")
    assert not hasattr(ContextStore, "transform")


def test_context_store_derives_context_by_deep_merging_the_base_context():
    store = ContextStore()
    store.add({"tenant": "t1", "attributes": {"region": "eu"}})

    derived = store.get_derived_context({"attributes": {"tier": "gold"}})

    assert derived == {"tenant": "t1", "attributes": {"region": "eu", "tier": "gold"}}


async def _response_for(httpserver: HTTPServer, status: int, body: str, content_type: Optional[str] = None):
    """Perform one real (localhost) request and hand the live aiohttp response to the caller."""
    httpserver.expect_request("/probe", method="GET").respond_with_data(
        body,
        status=status,
        content_type=content_type or "application/json",
        headers={"Location": "http://elsewhere.test/"},
    )
    url = httpserver.url_for("/probe")
    async with aiohttp.ClientSession() as session, session.get(url, allow_redirects=False) as response:
        yield response


@pytest.mark.parametrize("status", [200, 201, 204, 299])
async def test_handle_api_error_accepts_success_statuses(httpserver: HTTPServer, status: int):
    async for response in _response_for(httpserver, status, ""):
        assert await handle_api_error(response) is None


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_handle_api_error_rejects_redirect_statuses(httpserver: HTTPServer, status: int):
    """A redirect the client did not follow is not a successful API response."""
    async for response in _response_for(httpserver, status, "<html>Moved</html>", content_type="text/html"):
        with pytest.raises(PermitApiError) as exc_info:
            await handle_api_error(response)
        assert exc_info.value.status_code == status


def test_permit_connection_error_still_caught_by_the_deprecated_base():
    # Regression guard, not an endorsement. `PermitException` is deprecated,
    # but consumers on 2.6.x catch it, and re-parenting PermitConnectionError
    # onto PermitError would silently stop `except PermitException` from
    # catching connection failures. Re-parent it in a major version, not here.
    assert issubclass(PermitConnectionError, PermitException)


def test_permit_connection_error_is_still_a_permit_error():
    error = PermitConnectionError("boom")

    assert isinstance(error, PermitError)
    assert error.original_error is None


def test_check_query_context_is_optional():
    # bulk_check reads each check's context with .get(), so a query without one
    # is valid and the TypedDict must not make type checkers demand it.
    assert CheckQuery.__required_keys__ == {"user", "action", "resource"}
    assert CheckQuery.__optional_keys__ == {"context"}


REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"


def runtime_requirement(name: str, python_version: str) -> Requirement:
    """Return the one requirements.txt entry for `name` that applies on `python_version`.

    Lines are filtered exactly as setup.py's get_requirements() filters them, so a
    line setup.py would pass to setuptools but packaging cannot parse fails here.
    """
    lines = REQUIREMENTS.read_text().splitlines()
    requirements = [Requirement(line.strip()) for line in lines if line.strip() and not line.startswith("#")]
    environment = {"python_version": python_version, "python_full_version": f"{python_version}.0"}
    matching = [
        requirement
        for requirement in requirements
        if requirement.name == name and (requirement.marker is None or requirement.marker.evaluate(environment))
    ]
    assert len(matching) == 1, f"expected one {name} requirement on Python {python_version}, got {matching}"
    return matching[0]


def pydantic_release_candidates() -> list[str]:
    """Return the release numbers 1.0.0-1.10.29 and 2.0.0-2.19.29, plus "2.0".

    That covers every pydantic 1 and 2 release so far, so a test can ask which of
    them a specifier allows without reaching PyPI. "2.0" is how pydantic spelled
    its 2.0.0 release.
    """
    candidates = ["2.0"]
    for major, minor_count in ((1, 11), (2, 20)):
        for minor in range(minor_count):
            for patch in range(30):
                candidates.append(f"{major}.{minor}.{patch}")
    return candidates


PYDANTIC_CANDIDATES = pydantic_release_candidates()


@pytest.mark.parametrize("python_version", ["3.10", "3.11", "3.12", "3.13", "3.14"])
def test_pydantic_requirement_allows_no_release_affected_by_cve_2024_3772(python_version: str):
    # CVE-2024-3772 (ReDoS in email validation) is fixed in pydantic 1.10.13.
    # Under pydantic 2 permit validates emails with the pydantic.v1 copy pydantic
    # bundles, which is 1.10.13 or later only from pydantic 2.4.2.
    specifier = runtime_requirement("pydantic", python_version).specifier
    affected = [
        candidate
        for candidate in PYDANTIC_CANDIDATES
        if Version(candidate) < Version("1.10.13") or Version("2") <= Version(candidate) < Version("2.4.2")
    ]

    assert list(specifier.filter(affected)) == []


@pytest.mark.parametrize(
    ("python_version", "pydantic_1_floor", "pydantic_2_floor"),
    [
        ("3.10", "1.10.18", "2.4.2"),
        ("3.11", "1.10.18", "2.4.2"),
        ("3.12", "1.10.18", "2.4.2"),
        # pydantic 2.4.2-2.7.x need a pydantic-core with no Python 3.13 wheels.
        ("3.13", "1.10.18", "2.8.0"),
        ("3.14", "1.10.25", "2.13.0"),
    ],
)
def test_pydantic_requirement_allows_each_major_from_its_floor_up(
    python_version: str, pydantic_1_floor: str, pydantic_2_floor: str
):
    specifier = runtime_requirement("pydantic", python_version).specifier
    allowed = [Version(candidate) for candidate in specifier.filter(PYDANTIC_CANDIDATES)]
    candidates = [Version(candidate) for candidate in PYDANTIC_CANDIDATES]

    for major, floor in ((1, Version(pydantic_1_floor)), (2, Version(pydantic_2_floor))):
        expected = [candidate for candidate in candidates if candidate.major == major and candidate >= floor]
        assert [version for version in allowed if version.major == major] == expected


@pytest.mark.parametrize("python_version", ["3.10", "3.11", "3.12", "3.13"])
@pytest.mark.parametrize("version", ["1.10.13", "1.10.17"])
def test_pydantic_requirement_before_py314_rejects_1_10_17_and_older(python_version: str, version: str):
    # Up to 1.10.16 there is no pydantic.v1 package for type checkers to resolve
    # permit's model imports against, and up to 1.10.17 `import permit` emits
    # thousands of DeprecationWarnings on Python 3.13.
    assert not runtime_requirement("pydantic", python_version).specifier.contains(version)


@pytest.mark.parametrize("python_version", ["3.10", "3.11", "3.12", "3.13", "3.14"])
def test_pydantic_requirement_rejects_2_0(python_version: str):
    # pydantic 2.0's pydantic.v1.parse_obj_as builds a pydantic 2 model, so every
    # API call that parses a response raises TypeError.
    assert not runtime_requirement("pydantic", python_version).specifier.contains("2.0")


def test_pydantic_requirement_rejects_versions_that_crash_on_py314():
    specifier = runtime_requirement("pydantic", "3.14").specifier

    for crashing in ("1.10.24", "2.11.10", "2.12.5"):
        assert not specifier.contains(crashing), crashing
    for working in ("1.10.25", "1.10.26", "2.13.0", "2.13.5"):
        assert specifier.contains(working), working


@pytest.mark.parametrize(
    ("name", "python_version", "broken"),
    [
        # `import permit` raises AttributeError from typing_extensions.ParamSpec.
        ("typing-extensions", "3.13", "4.11.0"),
        # typing_extensions.TypedDict loses every key, so CheckQuery has none.
        ("typing-extensions", "3.14", "4.13.2"),
        # `import loguru` warns that asyncio.iscoroutinefunction is going away.
        ("loguru", "3.14", "0.7.2"),
    ],
)
def test_runtime_floor_excludes_versions_broken_on_a_supported_python(name: str, python_version: str, broken: str):
    assert not runtime_requirement(name, python_version).specifier.contains(broken)


def test_deprecated_decorator_keeps_async_functions_async():
    async def fetch():
        return None

    def compute():
        return None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async_wrapper = deprecated("use something else")(fetch)
        sync_wrapper = deprecated("use something else")(compute)

    assert inspect.iscoroutinefunction(async_wrapper)
    assert not inspect.iscoroutinefunction(sync_wrapper)
    assert [str(w.message) for w in caught if "asyncio.iscoroutinefunction" in str(w.message)] == []


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.10.13", (1, 10, 13)),
        ("2.13.5", (2, 13, 5)),
        ("2.0", (2, 0)),
        ("2.14.0b2", (2, 14, 0)),
        ("2.12.0a1", (2, 12, 0)),
        ("2.11.0rc1", (2, 11, 0)),
        ("2.13.0.dev0", (2, 13, 0)),
        ("2.13.5+local", (2, 13, 5)),
    ],
)
def test_pydantic_version_parses_release_and_pre_release_versions(version: str, expected: tuple[int, ...]):
    assert pydantic_version._parse(version) == expected


def test_pydantic_version_rejects_a_component_without_a_leading_number():
    with pytest.raises(ValueError, match=r"'x1'"):
        pydantic_version._parse("2.x1.0")


def test_pydantic_version_constant_is_the_installed_version():
    assert pydantic_version._parse(pydantic.__version__) == pydantic_version.PYDANTIC_VERSION
