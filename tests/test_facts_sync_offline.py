"""Offline tests for the headers that make the PDP wait for a proxied facts write.

With ``proxy_facts_via_pdp`` on, the SDK sends its facts requests to the PDP, with the
``X-Wait-Timeout`` header when a facts sync timeout is set (PER-16681). Each call goes
through the async and the blocking client, and the test checks the request it puts on the
wire (method, path, query string, headers and JSON body). Every request is served by a local
``pytest_httpserver``, the API and the PDP each on a server of their own, and the API context
is pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
from contextlib import nullcontext
from operator import attrgetter
from typing import Any

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.config import PermitConfig
from permit.sync import Permit as SyncPermit
from tests.utils import FACTS, Call, call, offline_config, sent

FLAVOURS = ["async", "sync"]

HEADERS = ("Authorization", "Content-Type", "X-Wait-Timeout", "X-Timeout-Policy")

ENVIRONMENT_ID = "6a1b2c3d-0000-4000-8000-000000000003"
PROJECT_ID = "6a1b2c3d-0000-4000-8000-000000000002"
ORGANIZATION_ID = "6a1b2c3d-0000-4000-8000-000000000001"
CREATED_AT = "2026-01-01T00:00:00+00:00"
USER = {
    "key": "alice",
    "id": "6a1b2c3d-0000-4000-8000-000000000010",
    "organization_id": ORGANIZATION_ID,
    "project_id": PROJECT_ID,
    "environment_id": ENVIRONMENT_ID,
    "created_at": CREATED_AT,
    "updated_at": CREATED_AT,
}

CREATE_USER = call("api.users.create", {"key": "alice"})
CREATE_USER_SENT = {"method": "POST", "path": "/facts/users", "query": [], "body": {"key": "alice"}}


@pytest.fixture
def pdp_server(httpserver_ipv4: HTTPServer) -> HTTPServer:
    """A server of its own for the PDP, so a request reaching it is told from one to the API."""
    return httpserver_ipv4


def make_config(api: HTTPServer, pdp: HTTPServer, **options: Any) -> PermitConfig:
    """An offline config for the API on ``api`` and the PDP on ``pdp``, with ``options``.

    The options go to ``PermitConfig`` itself, which validates them as it does for an
    application that passes them.
    """
    offline = offline_config(api.url_for("").rstrip("/"))
    return PermitConfig(
        token=offline.token,
        api_url=offline.api_url,
        pdp=pdp.url_for("").rstrip("/"),
        api_context=offline.api_context,
        **options,
    )


async def _invoke_async(config: PermitConfig, target: Call, wait: dict[str, Any] | None) -> object:
    async with Permit(config) as permit:
        with nullcontext(permit) if wait is None else permit.wait_for_sync(**wait) as client:
            return await attrgetter(target.path)(client)(*target.args, **target.kwargs)


def invoke(
    config: PermitConfig, flavour: str, target: Call, wait: dict[str, Any] | None = None
) -> object:
    """Call ``permit.<target.path>`` on the async or the blocking client, then close it.

    With ``wait``, the call goes through the client ``permit.wait_for_sync(**wait)`` yields.
    """
    if flavour == "async":
        return asyncio.run(_invoke_async(config, target, wait))
    with (
        SyncPermit(config) as permit,
        nullcontext(permit) if wait is None else permit.wait_for_sync(**wait) as client,
    ):
        result = attrgetter(target.path)(client)(*target.args, **target.kwargs)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


def facts_headers(wait_timeout: str | None, policy: str | None) -> dict[str, str | None]:
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json",
        "X-Wait-Timeout": wait_timeout,
        "X-Timeout-Policy": policy,
    }


# --- the timeout in the config ---------------------------------------------------------

# PermitConfig validates facts_sync_timeout as a float, so an int is sent as "3.0".
CONFIG_TIMEOUTS = {
    "unset": (None, None),
    "zero": (0, "0.0"),
    "zero-float": (0.0, "0.0"),
    "int": (3, "3.0"),
    "float": (2.5, "2.5"),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("timeout", "header"), CONFIG_TIMEOUTS.values(), ids=CONFIG_TIMEOUTS.keys()
)
def test_facts_sync_timeout_is_sent_unless_it_is_none(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    timeout: float | None,
    header: str | None,
    flavour: str,
) -> None:
    """0 is sent too, so the PDP answers without waiting instead of waiting its default."""
    config = make_config(
        httpserver, pdp_server, proxy_facts_via_pdp=True, facts_sync_timeout=timeout
    )
    pdp_server.expect_request("/facts/users", method="POST").respond_with_json(USER)

    invoke(config, flavour, CREATE_USER)

    [(request, _)] = pdp_server.log
    assert sent(request) == CREATE_USER_SENT
    assert sent_headers(request) == facts_headers(header, None)
    assert httpserver.log == []


# --- the timeout of wait_for_sync() ---------------------------------------------------

# wait_for_sync() sets the timeout it is given on its client's config as it is, so an int
# is sent as "3". Its own timeout replaces the config's, 0 included; its policy replaces
# the config's only when it is given.
WAIT_FOR_SYNC_TIMEOUTS = {
    "default": ({}, "10.0", "fail"),
    "zero": ({"timeout": 0}, "0", "fail"),
    "zero-float": ({"timeout": 0.0}, "0.0", "fail"),
    "int": ({"timeout": 3}, "3", "fail"),
    "float": ({"timeout": 2.5}, "2.5", "fail"),
    "zero-policy": ({"timeout": 0, "policy": "ignore"}, "0", "ignore"),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("wait", "header", "policy"),
    WAIT_FOR_SYNC_TIMEOUTS.values(),
    ids=WAIT_FOR_SYNC_TIMEOUTS.keys(),
)
def test_wait_for_sync_sends_its_timeout_even_when_it_is_zero(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    wait: dict[str, Any],
    header: str,
    policy: str,
    flavour: str,
) -> None:
    config = make_config(
        httpserver,
        pdp_server,
        proxy_facts_via_pdp=True,
        facts_sync_timeout=7.5,
        facts_sync_timeout_policy="fail",
    )
    pdp_server.expect_request("/facts/users", method="POST").respond_with_json(USER)

    invoke(config, flavour, CREATE_USER, wait)

    [(request, _)] = pdp_server.log
    assert sent(request) == CREATE_USER_SENT
    assert sent_headers(request) == facts_headers(header, policy)
    assert httpserver.log == []


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_without_proxy_facts_via_pdp_a_zero_timeout_sends_no_header(
    httpserver: HTTPServer, pdp_server: HTTPServer, flavour: str
) -> None:
    """The facts request goes to the API, which does not wait, so nothing tells it to."""
    config = make_config(
        httpserver, pdp_server, facts_sync_timeout=0, facts_sync_timeout_policy="fail"
    )
    httpserver.expect_request(f"{FACTS}/users", method="POST").respond_with_json(USER)

    invoke(config, flavour, CREATE_USER)

    [(request, _)] = httpserver.log
    assert sent(request) == {**CREATE_USER_SENT, "path": f"{FACTS}/users"}
    assert sent_headers(request) == facts_headers(None, None)
    assert pdp_server.log == []
