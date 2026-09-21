"""Offline regression tests.

These tests never reach the Permit REST API, a PDP, or any other remote host and
they need no API key: every request is served by a local ``pytest_httpserver``
instance, and the SDK context is pre-populated so no API-key scope lookup is
issued.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import aiohttp
import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit.api.context import ApiContext, ApiKeyAccessLevel
from permit.api.elements import ElementsApi
from permit.api.models import RoleAssignmentCreate, RoleAssignmentRemove
from permit.api.resource_instances import ResourceInstancesApi
from permit.api.users import UsersApi
from permit.config import PermitConfig
from permit.exceptions import (
    PermitApiError,
    PermitConnectionError,
    PermitContextError,
    PermitError,
    PermitException,
    handle_api_error,
)
from permit.pdp_api.pdp_api_client import SyncPDPApi
from permit.utils.context import ContextStore

ORG = "test-org"
PROJECT = "test-project"
ENVIRONMENT = "test-env"
FACTS = f"/v2/facts/{PROJECT}/{ENVIRONMENT}"


def offline_config(base_url: str, **overrides) -> PermitConfig:
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
    assert client._headers["Authorization"] == "bearer test-token"
    assert client._headers["Content-Type"] == "application/json"


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
