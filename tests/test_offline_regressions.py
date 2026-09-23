"""Offline regression tests.

These tests never reach the Permit REST API, a PDP, or any other remote host and
they need no API key: every request is served by a local ``pytest_httpserver``
instance, and the SDK context is pre-populated so no API-key scope lookup is
issued.
"""

import math
import subprocess
import sys
import warnings
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import aiohttp
import pydantic
import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import exceptions
from permit.api.context import ApiContext, ApiKeyAccessLevel
from permit.api.elements import ElementsApi
from permit.api.encoders import jsonable_encoder
from permit.api.models import RoleAssignmentCreate, RoleAssignmentRemove
from permit.api.resource_instances import ResourceInstancesApi
from permit.api.users import UsersApi
from permit.config import PermitConfig
from permit.enforcement.enforcer import CheckQuery
from permit.exceptions import (
    PermitApiError,
    PermitConnectionError,
    PermitContextError,
    PermitError,
    handle_api_error,
)
from permit.pdp_api.pdp_api_client import SyncPDPApi
from permit.utils import pydantic_version
from permit.utils.context import ContextStore

ORG = "test-org"
PROJECT = "test-project"
ENVIRONMENT = "test-env"
FACTS = f"/v2/facts/{PROJECT}/{ENVIRONMENT}"


def offline_config(base_url: str, **overrides: Any) -> PermitConfig:
    """Build a PermitConfig whose context is already resolved to environment level.

    This is the state the SDK holds after a successful ``/v2/api-key/scope``
    lookup, so no method under test needs to perform one.
    """
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


def role_assignment_read_payload() -> dict[str, Any]:
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


def user_read_payload(key: str) -> dict[str, Any]:
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
    assert len(httpserver.log) == 1, (
        f"expected exactly one request, got {[r.url for r, _ in httpserver.log]}"
    )
    return httpserver.log[0][0]


async def test_resource_instances_list_sends_detailed_filter_as_query_string(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """detailed_key must reach the wire as a string: yarl rejects bool query values."""
    httpserver.expect_request(f"{FACTS}/resource_instances", method="GET").respond_with_json([])

    await ResourceInstancesApi(config).list(detailed_key=True)

    assert single_request(httpserver).args["detailed"] == "true"


async def test_resource_instances_list_sends_detailed_false_as_query_string(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request(f"{FACTS}/resource_instances", method="GET").respond_with_json([])

    await ResourceInstancesApi(config).list(detailed_key=False)

    assert single_request(httpserver).args["detailed"] == "false"


async def test_resource_instances_list_omits_detailed_when_not_requested(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request(f"{FACTS}/resource_instances", method="GET").respond_with_json([])

    await ResourceInstancesApi(config).list()

    assert "detailed" not in single_request(httpserver).args


async def test_users_sync_does_not_mutate_the_caller_dict(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """The dict branch of users.sync() must not pop 'key' out of the caller's dict."""
    # an invalid email keeps pydantic's Union[UserCreate, dict] coercion on the dict branch
    user = {"key": "user-1", "email": "not-an-email"}
    httpserver.expect_request(f"{FACTS}/users/user-1", method="PUT").respond_with_json(
        user_read_payload("user-1")
    )

    await UsersApi(config).sync(user)

    assert user == {"key": "user-1", "email": "not-an-email"}


async def test_users_sync_dict_branch_is_reusable(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """A caller may retry with the same dict; the second call must not raise KeyError."""
    user = {"key": "user-1", "email": "not-an-email"}
    httpserver.expect_request(f"{FACTS}/users/user-1", method="PUT").respond_with_json(
        user_read_payload("user-1")
    )
    api = UsersApi(config)

    await api.sync(user)
    await api.sync(user)

    assert len(httpserver.log) == 2


async def test_users_assign_role_strips_unset_optional_fields(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """users.assign_role must match role_assignments.assign and not transmit explicit nulls."""
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="POST").respond_with_json(
        role_assignment_read_payload()
    )

    await UsersApi(config).assign_role(
        RoleAssignmentCreate(user="user-1", role="admin", tenant="tenant-1")
    )

    assert single_request(httpserver).get_json() == {"role": "admin", "tenant": "tenant-1"}


async def test_users_unassign_role_strips_unset_optional_fields(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="DELETE").respond_with_data(
        "", status=204
    )

    await UsersApi(config).unassign_role(
        RoleAssignmentRemove(user="user-1", role="admin", tenant="tenant-1")
    )

    assert single_request(httpserver).get_json() == {"role": "admin", "tenant": "tenant-1"}


async def test_users_assign_role_keeps_explicitly_provided_resource_instance(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request(f"{FACTS}/users/user-1/roles", method="POST").respond_with_json(
        role_assignment_read_payload()
    )

    await UsersApi(config).assign_role(
        RoleAssignmentCreate(
            user="user-1", role="admin", tenant="tenant-1", resource_instance="doc:readme"
        )
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
        (
            ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY,
            ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY,
        ),
    ],
)
async def test_ensure_access_level_accepts_a_key_broad_enough_for_the_endpoint(
    config: PermitConfig, permitted: ApiKeyAccessLevel, required: ApiKeyAccessLevel
) -> None:
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
) -> None:
    api = UsersApi(config)
    api.config.api_context._permitted_access_level = permitted

    with pytest.raises(PermitContextError):
        await api._ensure_access_level(required)


def test_sync_pdp_api_initializes_the_base_client_state(config: PermitConfig) -> None:
    """SyncPDPApi must run PermitPdpApiClient.__init__, not skip it."""
    client = SyncPDPApi(config)

    assert client._config is config
    assert client._base_url == config.pdp
    assert client._headers["Authorization"] == "bearer test-token"
    assert client._headers["Content-Type"] == "application/json"


async def test_elements_login_as_sends_canonical_uuid_strings(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
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


async def test_elements_login_as_passes_string_ids_through(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request("/v2/auth/elements_login_as", method="POST").respond_with_json(
        {"redirect_url": "http://elements.permit.test/login"}
    )

    await ElementsApi(config).login_as("user-1", "tenant-1")

    assert single_request(httpserver).get_json() == {"user_id": "user-1", "tenant_id": "tenant-1"}


def test_context_store_exposes_no_silently_ignored_transform_api() -> None:
    """register_transform()/transform() were dead: the enforcer never consulted them."""
    assert not hasattr(ContextStore, "register_transform")
    assert not hasattr(ContextStore, "transform")


def test_context_store_derives_context_by_deep_merging_the_base_context() -> None:
    store = ContextStore()
    store.add({"tenant": "t1", "attributes": {"region": "eu"}})

    derived = store.get_derived_context({"attributes": {"tier": "gold"}})

    assert derived == {"tenant": "t1", "attributes": {"region": "eu", "tier": "gold"}}


async def _response_for(
    httpserver: HTTPServer, status: int, body: str, content_type: str | None = None
) -> AsyncIterator[aiohttp.ClientResponse]:
    """Perform one real (localhost) request and hand the live aiohttp response to the caller."""
    httpserver.expect_request("/probe", method="GET").respond_with_data(
        body,
        status=status,
        content_type=content_type or "application/json",
        headers={"Location": "http://elsewhere.test/"},
    )
    url = httpserver.url_for("/probe")
    async with (
        aiohttp.ClientSession() as session,
        session.get(url, allow_redirects=False) as response,
    ):
        yield response


@pytest.mark.parametrize("status", [200, 201, 204, 299])
async def test_handle_api_error_accepts_success_statuses(
    httpserver: HTTPServer, status: int
) -> None:
    async for response in _response_for(httpserver, status, ""):
        await handle_api_error(response)  # accepted: does not raise


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_handle_api_error_rejects_redirect_statuses(
    httpserver: HTTPServer, status: int
) -> None:
    """A redirect the client did not follow is not a successful API response."""
    async for response in _response_for(
        httpserver, status, "<html>Moved</html>", content_type="text/html"
    ):
        with pytest.raises(PermitApiError) as exc_info:
            await handle_api_error(response)
        assert exc_info.value.status_code == status


def test_permit_connection_error_still_caught_by_the_deprecated_base() -> None:
    # Regression guard, not an endorsement. `PermitException` is deprecated,
    # but consumers on 2.6.x catch it, and re-parenting PermitConnectionError
    # onto PermitError would silently stop `except PermitException` from
    # catching connection failures. Re-parent it in a major version, not here.
    assert issubclass(PermitConnectionError, exceptions.PermitException)  # type: ignore[deprecated]


def test_permit_connection_error_is_still_a_permit_error() -> None:
    error = PermitConnectionError("boom")

    assert isinstance(error, PermitError)
    assert error.original_error is None


def test_check_query_context_is_optional() -> None:
    # bulk_check reads each check's context with .get(), so a query without one
    # is valid and the TypedDict must not make type checkers demand it.
    assert CheckQuery.__required_keys__ == {"user", "action", "resource"}
    assert CheckQuery.__optional_keys__ == {"context"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal(1), 1),
        (Decimal("1E+2"), 100),
        (Decimal("1.0"), 1.0),
        (Decimal("-2.5"), -2.5),
        (Decimal("Infinity"), math.inf),
        (Decimal("-Infinity"), -math.inf),
    ],
)
def test_jsonable_encoder_encodes_decimals(value: Decimal, expected: float) -> None:
    encoded = jsonable_encoder({"value": value})["value"]

    assert encoded == expected
    assert type(encoded) is type(expected)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("-NaN")])
def test_jsonable_encoder_encodes_decimal_nan_as_float_nan(value: Decimal) -> None:
    # A non-finite Decimal has a str exponent ("n" or "F"), which used to be
    # compared with 0 and raise TypeError.
    encoded = jsonable_encoder([value])[0]

    assert isinstance(encoded, float)
    assert math.isnan(encoded)


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
def test_pydantic_version_parses_release_and_pre_release_versions(
    version: str, expected: tuple[int, ...]
) -> None:
    assert pydantic_version._parse(version) == expected


def test_pydantic_version_rejects_a_component_without_a_leading_number() -> None:
    with pytest.raises(ValueError, match=r"'x1'"):
        pydantic_version._parse("2.x1.0")


def test_pydantic_version_constant_is_the_installed_version() -> None:
    assert pydantic_version._parse(pydantic.__version__) == pydantic_version.PYDANTIC_VERSION


def test_importing_the_sdk_emits_no_deprecation_warning() -> None:
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", "import permit"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_permit_exception_still_warns_when_instantiated() -> None:
    with pytest.warns(DeprecationWarning, match="Use PermitError instead"):
        exceptions.PermitException("boom")  # type: ignore[deprecated]


def test_permit_exception_still_warns_when_subclassed() -> None:
    with pytest.warns(DeprecationWarning, match="Use PermitError instead"):

        class _Custom(exceptions.PermitException):  # type: ignore[deprecated]
            pass


def test_permit_connection_error_instantiation_does_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        PermitConnectionError("boom")
