"""Offline tests for permit.api.pdps (PER-16337).

``refresh()`` is called through the async and the blocking client, and the tests check the
request it puts on the wire (method, path, query string, headers and JSON body) and what the
response parses into. Every request is served by a local ``pytest_httpserver`` and the API
context is pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
from operator import attrgetter
from typing import Any, NamedTuple
from uuid import UUID

import pytest
from pydantic.v1 import ValidationError
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.api.models import PDPDataRefreshResponse
from permit.api.pdps import PdpsApi
from permit.config import PermitConfig
from permit.exceptions import (
    PermitApiDetailedError,
    PermitApiError,
    PermitContextError,
    PermitNotFoundError,
)
from permit.sync import Permit as SyncPermit
from tests.utils import ENVIRONMENT, ORG, PROJECT, Call, call, sent

FLAVOURS = ["async", "sync"]
REFRESH = f"/v2/pdps/{PROJECT}/{ENVIRONMENT}/configs/refresh"

# The headers the SDK sets. The wait-for-sync ones are listed so that sending one shows.
HEADERS = ("Authorization", "Content-Type", "X-Wait-Timeout", "X-Timeout-Policy")
JSON_HEADERS: dict[str, str | None] = {
    "Authorization": "Bearer test-token",
    "Content-Type": "application/json",
    "X-Wait-Timeout": None,
    "X-Timeout-Policy": None,
}

UPDATE_ID = "00000000-0000-4000-8000-000000000040"
PDP_IDS = ["00000000-0000-4000-8000-000000000041", "00000000-0000-4000-8000-000000000042"]
REFRESHED = {"update_id": UPDATE_ID, "pdp_ids": PDP_IDS}


class Case(NamedTuple):
    """One refresh() call and the JSON body it must send."""

    call: Call
    body: dict[str, Any]


CASES = {
    "no-reason": Case(call("refresh"), {}),
    "reason": Case(call("refresh", "nightly import"), {"reason": "nightly import"}),
    "reason-keyword": Case(call("refresh", reason="sync"), {"reason": "sync"}),
    "reason-none": Case(call("refresh", reason=None), {}),
    "reason-unicode": Case(call("refresh", "réimport ✓"), {"reason": "réimport ✓"}),
    "reason-512-characters": Case(call("refresh", "r" * 512), {"reason": "r" * 512}),
}


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``permit.api.pdps.<target.path>`` on the async or the blocking client."""
    permit = Permit(config) if flavour == "async" else SyncPermit(config)
    result = attrgetter(f"api.pdps.{target.path}")(permit)(*target.args, **target.kwargs)
    if flavour == "async":
        return asyncio.run(result)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


def test_refresh_is_the_only_public_method() -> None:
    public = {
        name
        for name, value in vars(PdpsApi).items()
        if not name.startswith("_") and callable(value)
    }

    assert public == {"refresh"}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_refresh_posts_the_reason_to_the_environment_refresh_route(
    httpserver: HTTPServer, config: PermitConfig, case: Case, flavour: str
) -> None:
    httpserver.expect_request(REFRESH, method="POST").respond_with_json(REFRESHED)

    invoke(config, flavour, case.call)

    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": "POST", "path": REFRESH, "query": [], "body": case.body}
    ]
    assert [sent_headers(request) for request, _ in httpserver.log] == [JSON_HEADERS]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_refresh_returns_the_update_id_and_the_targeted_pdps(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    httpserver.expect_request(REFRESH, method="POST").respond_with_json(REFRESHED)

    result = invoke(config, flavour, call("refresh"))

    assert type(result) is PDPDataRefreshResponse
    assert result.update_id == UUID(UPDATE_ID)
    assert result.pdp_ids == [UUID(pdp_id) for pdp_id in PDP_IDS]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_refresh_goes_to_the_api_even_with_proxy_facts_via_pdp(
    httpserver: HTTPServer, httpserver_ipv4: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    """The PDPs are refreshed by the Permit API, so the request never goes to a PDP."""
    config.pdp = httpserver_ipv4.url_for("").rstrip("/")
    config.proxy_facts_via_pdp = True
    httpserver.expect_request(REFRESH, method="POST").respond_with_json(REFRESHED)

    invoke(config, flavour, call("refresh"))

    assert [sent(request)["path"] for request, _ in httpserver.log] == [REFRESH]
    assert [sent_headers(request) for request, _ in httpserver.log] == [JSON_HEADERS]
    assert httpserver_ipv4.log == []


class ApiError(NamedTuple):
    """An error status, the error code the API sends with it, and what the SDK raises."""

    status: int
    error_code: str
    raises: type[PermitApiError]


API_ERRORS = {
    "read-only-key": ApiError(403, "FORBIDDEN_ACCESS", PermitApiDetailedError),
    "no-pdp-configuration": ApiError(404, "NOT_FOUND", PermitNotFoundError),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("error", API_ERRORS.values(), ids=API_ERRORS.keys())
def test_refresh_raises_the_matching_permit_api_error(
    httpserver: HTTPServer, config: PermitConfig, error: ApiError, flavour: str
) -> None:
    detail = {
        "id": "request-1",
        "title": f"status {error.status}",
        "error_code": error.error_code,
        "message": f"status {error.status}",
    }
    httpserver.expect_request(REFRESH, method="POST").respond_with_json(detail, status=error.status)

    with pytest.raises(PermitApiError) as raised:
        invoke(config, flavour, call("refresh"))

    assert type(raised.value) is error.raises
    assert raised.value.status_code == error.status
    assert raised.value.details == detail
    assert len(httpserver.log) == 1


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_refresh_rejects_a_reason_over_512_characters_before_sending(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    with pytest.raises(ValidationError):
        invoke(config, flavour, call("refresh", "r" * 513))

    assert httpserver.log == []


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_refresh_refuses_a_project_context_before_sending(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    """A project-level key needs the SDK's API context set to an environment first."""
    config.api_context._save_api_key_accessible_scope(org=ORG, project=PROJECT)
    config.api_context.set_project_level_context(ORG, PROJECT)

    with pytest.raises(PermitContextError):
        invoke(config, flavour, call("refresh"))

    assert httpserver.log == []
