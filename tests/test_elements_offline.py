"""Offline tests for permit.elements.login_as() (PER-16177).

It is called through the async and the blocking client, each closed once the call returns,
and the test checks the request it puts on the wire (method, path, query string, headers
and JSON body), what the response parses into, and that the API's error response raises
the matching ``PermitApiError``. Every request is served by a local ``pytest_httpserver``
and the API context is pre-populated, so no API key and no ``/v2/api-key/scope`` lookup
are needed.
"""

import asyncio
import inspect
from uuid import UUID

import pytest
from pytest_httpserver import HTTPServer

from permit import Permit
from permit.api.elements import UserLoginAsResponse
from permit.config import PermitConfig
from permit.exceptions import PermitApiError, PermitNotFoundError
from permit.sync import Permit as SyncPermit
from tests.utils import sent

FLAVOURS = ["async", "sync"]
LOGIN_AS = "/v2/auth/elements_login_as"
USER_ID = "01234567-89ab-cdef-0123-456789abcdef"
TENANT_ID = "fedcba98-7654-3210-fedc-ba9876543210"
TICKET = {"redirect_url": "https://app.example.com/login?token=abc", "token": "abc"}

# The ids login_as() is called with, and the ids it sends.
IDS: dict[str, tuple[str | UUID, str | UUID, dict[str, str]]] = {
    "keys": ("alice", "acme", {"user_id": "alice", "tenant_id": "acme"}),
    "uuids": (UUID(USER_ID), UUID(TENANT_ID), {"user_id": USER_ID, "tenant_id": TENANT_ID}),
}


async def _login_as_async(
    config: PermitConfig, user: str | UUID, tenant: str | UUID
) -> UserLoginAsResponse:
    async with Permit(config) as permit:
        return await permit.elements.login_as(user, tenant)


def login_as(
    config: PermitConfig, flavour: str, user: str | UUID, tenant: str | UUID
) -> UserLoginAsResponse:
    """Call ``permit.elements.login_as()`` on a new async or blocking client, then close it."""
    if flavour == "async":
        return asyncio.run(_login_as_async(config, user, tenant))
    with SyncPermit(config) as permit:
        result = permit.elements.login_as(user, tenant)
    assert not inspect.isawaitable(result)
    return result


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(("user", "tenant", "body"), IDS.values(), ids=IDS.keys())
def test_login_as_request_and_response(
    *,
    httpserver: HTTPServer,
    config: PermitConfig,
    user: str | UUID,
    tenant: str | UUID,
    body: dict[str, str],
    flavour: str,
) -> None:
    """The response gets ``content``, which holds the redirect URL for a header login."""
    httpserver.expect_request(LOGIN_AS, method="POST").respond_with_json(TICKET)

    result = login_as(config, flavour, user, tenant)

    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": "POST", "path": LOGIN_AS, "query": [], "body": body}
    ]
    assert [
        (request.headers.get("Authorization"), request.headers.get("Content-Type"))
        for request, _ in httpserver.log
    ] == [("Bearer test-token", "application/json")]
    assert type(result) is UserLoginAsResponse
    assert result == UserLoginAsResponse(**TICKET, content={"url": TICKET["redirect_url"]})


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_login_as_raises_the_api_error_for_an_unknown_user(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    detail = {
        "id": "6a1b2c3d0000400080000000000000ee",
        "title": "Not found",
        "error_code": "NOT_FOUND",
        "message": "The user alice was not found.",
    }
    httpserver.expect_request(LOGIN_AS, method="POST").respond_with_json(detail, status=404)

    with pytest.raises(PermitApiError) as raised:
        login_as(config, flavour, "alice", "acme")

    assert type(raised.value) is PermitNotFoundError
    assert raised.value.status_code == 404
    assert raised.value.details == detail
    assert len(httpserver.log) == 1
