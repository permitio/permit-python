"""Offline tests for the routes only the container PDP serves (PER-16340).

The hosted cloud PDP serves the decision routes and ``/health``. It answers 404, with an
empty body, for the routes it does not serve: ``/user-tenants``, which
``get_user_tenants()`` calls; the ``/local`` routes of ``permit.pdp_api``; and the
``/facts`` routes that the facts methods of ``permit.api`` call with
``proxy_facts_via_pdp`` on. The SDK raises that 404 as an error that names the route and
says it needs the container PDP, and keeps its usual error for a 404 that is a real "not
found": a container PDP's, which has a JSON body, or the API's, which a container PDP's
``/facts`` routes pass on. A client created with ``proxy_facts_via_pdp`` on and the cloud
PDP as its ``pdp`` warns, at the line that created it.

Each call goes through the async and the blocking client, each closed once the call
returns. Every request is served by a local ``pytest_httpserver`` and the API context is
pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
import socket
import sys
import warnings
from collections.abc import Iterator
from operator import attrgetter
from typing import Any, Literal

import aiohttp
import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import ErrorCode, Permit, PermitConnectionError
from permit.config import PermitConfig
from permit.exceptions import PermitApiError, PermitNotFoundError
from permit.sync import Permit as SyncPermit
from tests.facts_methods import ALIASES, CASES, NEW_USER, Case, on_pdp, page
from tests.utils import CLOUD_PDP_URL, Call, call, sent

FLAVOURS = ["async", "sync"]
CLOUD_PDP_HOST = "cloudpdp.api.permit.io"
DOCS_LINK = "https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
USE_A_CONTAINER_PDP = "Point the SDK's `pdp` setting at a container PDP to use it."
USE_A_CONTAINER_PDP_FOR_FACTS = (
    "Point the SDK's `pdp` setting at a container PDP to use it, or turn proxy_facts_via_pdp "
    "off to send facts to the Permit REST API."
)

# The headers the SDK sets. The wait-for-sync ones are listed so that sending one shows.
HEADERS = ("Authorization", "Content-Type", "X-Wait-Timeout", "X-Timeout-Policy")
JSON_HEADERS: dict[str, str | None] = {
    "Authorization": "Bearer test-token",
    "Content-Type": "application/json",
    "X-Wait-Timeout": None,
    "X-Timeout-Policy": None,
}


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``permit.<target.path>`` on a new async or blocking client, and close the client."""
    if flavour == "async":

        async def call_awaiting() -> object:
            async with Permit(config) as permit:
                return await attrgetter(target.path)(permit)(*target.args, **target.kwargs)

        return asyncio.run(call_awaiting())
    with SyncPermit(config) as permit:
        result = attrgetter(target.path)(permit)(*target.args, **target.kwargs)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


def container_pdp_only(route: str, pdp_url: str, advice: str) -> str:
    """The message of the error for the cloud PDP's 404 for ``route``."""
    return (
        f"The SDK got status code 404 from the PDP at {pdp_url}: only the container PDP "
        f"serves {route}, and the cloud PDP does not.\n"
        f"{advice}\n"
        f"Read more about setting up the PDP at {DOCS_LINK}"
    )


@pytest.fixture
def pdp_server(httpserver_ipv4: HTTPServer) -> HTTPServer:
    """A server of its own for the PDP, so a request reaching it is told from one to the API."""
    return httpserver_ipv4


@pytest.fixture
def split_config(config: PermitConfig, pdp_server: HTTPServer) -> PermitConfig:
    """The offline config with the API on ``httpserver`` and the PDP on ``pdp_server``."""
    config.pdp = pdp_server.url_for("").rstrip("/")
    return config


@pytest.fixture
def cloud_pdp_url(pdp_server: HTTPServer, monkeypatch: pytest.MonkeyPatch) -> str:
    """A cloud PDP address whose host resolves to ``pdp_server``, on its port."""
    # aiohttp resolves names with socket.getaddrinfo unless aiodns is installed.
    assert aiohttp.resolver.DefaultResolver is aiohttp.ThreadedResolver, (
        "aiohttp resolves names without socket.getaddrinfo here; uninstall aiodns"
    )
    resolve = socket.getaddrinfo

    def resolve_the_cloud_pdp_locally(
        host: bytes | str | None, *args: Any, **kwargs: Any
    ) -> list[Any]:
        return resolve("127.0.0.1" if host == CLOUD_PDP_HOST else host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve_the_cloud_pdp_locally)
    return f"http://{CLOUD_PDP_HOST}:{pdp_server.port}"


# --- get_user_tenants() ---------------------------------------------------------------


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_get_user_tenants_names_the_route_and_asks_for_a_container_pdp(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    httpserver.expect_request("/user-tenants", method="POST").respond_with_data("", status=404)

    with pytest.raises(PermitConnectionError) as raised:
        invoke(config, flavour, call("get_user_tenants", "alice"))

    assert str(raised.value) == (
        f"permit.get_user_tenants() got status code 404 from the PDP at {config.pdp}: only "
        "the container PDP serves /user-tenants, and the cloud PDP does not.\n"
        "Point the SDK's `pdp` setting at a container PDP to use it.\n"
        f"Read more about setting up the PDP at {DOCS_LINK}"
    )


# --- facts through the PDP ------------------------------------------------------------


# The facts methods that send their request to the PDP with proxy_facts_via_pdp on: all but
# tenants.create_user(), which always goes to the API.
PDP_CASES = {name: case for name, case in CASES.items() if on_pdp(case)}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", PDP_CASES.values(), ids=PDP_CASES.keys())
def test_a_facts_method_raises_the_cloud_pdp_404_as_an_api_error_that_asks_for_a_container_pdp(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    case: Case,
    flavour: str,
) -> None:
    split_config.proxy_facts_via_pdp = True
    pdp_server.expect_request(case.path, method=case.method).respond_with_data("", status=404)

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, case.call)

    message = container_pdp_only(
        f"{case.method} {case.path}", split_config.pdp, USE_A_CONTAINER_PDP_FOR_FACTS
    )
    assert type(raised.value) is PermitApiError
    assert str(raised.value) == message
    assert raised.value.message == message
    assert raised.value.details == {"details": "", "message": message}
    assert raised.value.status_code == 404
    assert [sent(request) for request, _ in pdp_server.log] == [case.request]
    assert [sent_headers(request) for request, _ in pdp_server.log] == [JSON_HEADERS]
    assert httpserver.log == []


NOT_FOUND_DETAILS = {
    "id": "request-1",
    "title": "The requested data was not found",
    "error_code": "NOT_FOUND",
    "message": "Tenant with key 'acme' was not found.",
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    "case",
    [CASES["tenants.delete"], CASES["users.update"]],
    ids=["tenants.delete", "users.update"],
)
def test_the_apis_404_through_a_container_pdp_keeps_its_not_found_error(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    case: Case,
    flavour: str,
) -> None:
    """A container PDP's /facts routes pass on the API's 404 for an object that is missing."""
    split_config.proxy_facts_via_pdp = True
    pdp_server.expect_request(case.path, method=case.method).respond_with_json(
        NOT_FOUND_DETAILS, status=404
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, case.call)

    assert type(raised.value) is PermitNotFoundError
    assert str(raised.value) == (
        f"The requested data was not found ({ErrorCode.NOT_FOUND})\n"
        "Tenant with key 'acme' was not found.\n"
        "For more information: https://permit-io.slack.com/ssb/redirect (Request ID: request-1)"
    )
    assert raised.value.details == NOT_FOUND_DETAILS
    assert len(pdp_server.log) == 1
    assert httpserver.log == []


# A route of each kind that only the container PDP serves, and a call that requests it.
container_pdp_only_routes = pytest.mark.parametrize(
    ("proxy_facts_via_pdp", "method", "path", "target"),
    [
        (True, "POST", "/facts/users", CASES["users.create"].call),
        (False, "GET", "/local/role_assignments", call("pdp_api.role_assignments.list")),
    ],
    ids=["facts", "pdp_api"],
)


@pytest.mark.parametrize("flavour", FLAVOURS)
@container_pdp_only_routes
def test_a_container_pdps_own_404_keeps_the_api_error_it_raised(
    *,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    proxy_facts_via_pdp: bool,
    method: str,
    path: str,
    target: Call,
    flavour: str,
) -> None:
    """A container PDP answers a route it does not serve with a JSON 404."""
    split_config.proxy_facts_via_pdp = proxy_facts_via_pdp
    pdp_server.expect_request(path, method=method).respond_with_json(
        {"detail": "Not Found"}, status=404
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, target)

    assert type(raised.value) is PermitApiError
    assert str(raised.value) == "404 API Error: {'detail': 'Not Found'}"
    assert raised.value.details == {"detail": "Not Found"}


@pytest.mark.parametrize("flavour", FLAVOURS)
@container_pdp_only_routes
def test_a_404_whose_body_is_only_whitespace_keeps_the_api_error_it_raised(
    *,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    proxy_facts_via_pdp: bool,
    method: str,
    path: str,
    target: Call,
    flavour: str,
) -> None:
    """Only a 404 with no body at all is the cloud PDP's, away from its address."""
    split_config.proxy_facts_via_pdp = proxy_facts_via_pdp
    pdp_server.expect_request(path, method=method).respond_with_data(
        " \n", status=404, content_type="text/plain"
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, target)

    assert type(raised.value) is PermitApiError
    assert str(raised.value) == "404 API Error: {'details': ' \\n'}"
    assert raised.value.details == {"details": " \n"}
    assert len(pdp_server.log) == 1


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_apis_empty_404_keeps_its_api_error_with_proxy_facts_via_pdp_off(
    httpserver: HTTPServer, pdp_server: HTTPServer, split_config: PermitConfig, flavour: str
) -> None:
    """Only the PDP's container-only routes read an empty 404 as the cloud PDP's."""
    path = "/v2/facts/test-project/test-env/users"
    httpserver.expect_request(path, method="POST").respond_with_data("", status=404)

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, CASES["users.create"].call)

    assert type(raised.value) is PermitApiError
    assert str(raised.value) == "404 API Error: {'details': ''}"
    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": "POST", "path": path, "query": [], "body": NEW_USER}
    ]
    assert pdp_server.log == []


# --- permit.pdp_api -------------------------------------------------------------------


LOCAL_ROLE_ASSIGNMENTS = "/local/role_assignments"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_pdp_api_raises_the_cloud_pdp_404_as_an_api_error_that_asks_for_a_container_pdp(
    httpserver: HTTPServer, pdp_server: HTTPServer, split_config: PermitConfig, flavour: str
) -> None:
    pdp_server.expect_request(LOCAL_ROLE_ASSIGNMENTS, method="GET").respond_with_data(
        "", status=404
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, call("pdp_api.role_assignments.list", user_key="alice"))

    message = container_pdp_only(
        f"GET {LOCAL_ROLE_ASSIGNMENTS}", split_config.pdp, USE_A_CONTAINER_PDP
    )
    assert type(raised.value) is PermitApiError
    assert str(raised.value) == message
    assert raised.value.details == {"details": "", "message": message}
    assert [sent(request) for request, _ in pdp_server.log] == [
        {
            "method": "GET",
            "path": LOCAL_ROLE_ASSIGNMENTS,
            "query": list(page(user="alice")),
            "body": None,
        }
    ]
    assert [sent_headers(request) for request, _ in pdp_server.log] == [JSON_HEADERS]
    assert httpserver.log == []


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("status", [401, 500])
def test_another_empty_error_status_keeps_the_api_error_it_raised(
    pdp_server: HTTPServer, split_config: PermitConfig, status: int, flavour: str
) -> None:
    pdp_server.expect_request(LOCAL_ROLE_ASSIGNMENTS).respond_with_data("", status=status)

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, call("pdp_api.role_assignments.list"))

    assert type(raised.value) is PermitApiError
    assert str(raised.value) == f"{status} API Error: {{'details': ''}}"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_any_404_from_the_cloud_pdps_host_asks_for_a_container_pdp(
    pdp_server: HTTPServer, split_config: PermitConfig, cloud_pdp_url: str, flavour: str
) -> None:
    """At the cloud PDP's address, a 404 with a body counts as the cloud PDP's too."""
    split_config.pdp = cloud_pdp_url
    pdp_server.expect_request(LOCAL_ROLE_ASSIGNMENTS).respond_with_data(
        '{"detail": "Not Found"}', status=404, content_type="application/json"
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, call("pdp_api.role_assignments.list"))

    message = container_pdp_only(
        f"GET {LOCAL_ROLE_ASSIGNMENTS}", cloud_pdp_url, USE_A_CONTAINER_PDP
    )
    assert type(raised.value) is PermitApiError
    assert str(raised.value) == message
    assert raised.value.details == {"details": '{"detail": "Not Found"}', "message": message}
    assert len(pdp_server.log) == 1


# --- docstrings -----------------------------------------------------------------------


# The facts methods that send their request to the PDP's /facts routes with
# proxy_facts_via_pdp on, and those that always go to the Permit REST API.
FACTS_METHODS = [f"api.{name}" for name in PDP_CASES]
API_ONLY = [
    f"api.{name}" for name in [*CASES, *ALIASES] if not on_pdp(CASES[ALIASES.get(name, name)])
]
FACTS_NOTE = (
    "Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the PDP's "
    "``/facts`` routes, which the cloud PDP does not serve. It answers 404, which this method "
    "raises as a ``PermitApiError`` that says so."
)
NOTES = {
    **dict.fromkeys(FACTS_METHODS, FACTS_NOTE),
    "pdp_api.role_assignments.list": (
        "Container PDP only: the cloud PDP does not serve ``/local/role_assignments``. It "
        "answers 404, which this method raises as a ``PermitApiError`` that says so."
    ),
    "get_user_tenants": (
        "Container PDP only: the cloud PDP does not serve this query. It answers 404, which "
        "this method raises as a ``PermitConnectionError`` that says so."
    ),
}


@pytest.fixture(params=FLAVOURS)
def client(request: pytest.FixtureRequest, config: PermitConfig) -> Iterator[Permit]:
    """An async or a blocking client, whose methods are only read, closed after the test."""
    if request.param == "async":
        permit = Permit(config)
        yield permit
        asyncio.run(permit.close())
    else:
        with SyncPermit(config) as blocking:
            yield blocking


def docstring(client: Permit, path: str) -> str:
    """The docstring of ``client.<path>``, with each run of whitespace made one space."""
    return " ".join((inspect.getdoc(attrgetter(path)(client)) or "").split())


@pytest.mark.parametrize("path", NOTES.keys())
def test_a_container_pdp_only_method_says_so_in_its_docstring(client: Permit, path: str) -> None:
    assert NOTES[path] in docstring(client, path)


@pytest.mark.parametrize("path", API_ONLY)
def test_a_facts_api_method_that_always_goes_to_the_api_does_not_say_container_pdp_only(
    client: Permit, path: str
) -> None:
    assert "Container PDP only" not in docstring(client, path)


# --- the warning at creation ----------------------------------------------------------


def facts_proxied_to_the_cloud_pdp(pdp_url: str) -> str:
    return (
        "proxy_facts_via_pdp is on, so the facts methods of permit.api send their requests to "
        f"the PDP's /facts routes, but pdp is the cloud PDP ({pdp_url}), which does not serve "
        "them: each of those requests will fail with status code 404. Point pdp at a container "
        "PDP, or turn proxy_facts_via_pdp off to send facts to the Permit REST API."
    )


def create(config: PermitConfig, flavour: str) -> Permit:
    return Permit(config) if flavour == "async" else SyncPermit(config)


def close(client: Permit) -> None:
    if isinstance(client, SyncPermit):
        client.close()
    else:
        asyncio.run(client.close())


def caught_as_issued(caught: list[warnings.WarningMessage]) -> list[tuple[Any, ...]]:
    return [(w.category, str(w.message), w.filename, w.lineno) for w in caught]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_client_that_proxies_facts_to_the_cloud_pdp_warns_at_the_line_that_created_it(
    config: PermitConfig, flavour: str
) -> None:
    config.pdp = CLOUD_PDP_URL
    config.proxy_facts_via_pdp = True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        line = sys._getframe().f_lineno + 1
        client = Permit(config) if flavour == "async" else SyncPermit(config)
    close(client)

    assert caught_as_issued(caught) == [
        (UserWarning, facts_proxied_to_the_cloud_pdp(CLOUD_PDP_URL), __file__, line)
    ]


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("pdp", "proxy_facts_via_pdp"),
    [("http://localhost:7766", True), (CLOUD_PDP_URL, False), ("http://localhost:7766", False)],
    ids=["container-pdp", "proxy-off", "container-pdp-proxy-off"],
)
def test_no_warning_without_both_the_facts_proxy_and_the_cloud_pdp(
    *, config: PermitConfig, pdp: str, proxy_facts_via_pdp: bool, flavour: str
) -> None:
    config.pdp = pdp
    config.proxy_facts_via_pdp = proxy_facts_via_pdp

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = create(config, flavour)
    close(client)

    assert caught == []


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    "pdp", ["HTTPS://CloudPDP.API.permit.io:443/v1/", "http://cloudpdp.api.permit.io:7766"]
)
def test_any_address_on_the_cloud_pdps_host_warns(
    config: PermitConfig, pdp: str, flavour: str
) -> None:
    """The address's scheme, port, path and letter case do not matter, only its host."""
    config.pdp = pdp
    config.proxy_facts_via_pdp = True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = create(config, flavour)
    close(client)

    assert [(w.category, str(w.message)) for w in caught] == [
        (UserWarning, facts_proxied_to_the_cloud_pdp(pdp))
    ]


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    "pdp",
    [
        "http://localhost:7766/cloudpdp.api.permit.io",
        "https://cloudpdp.api.permit.io.example.com",
        "https://example.com/?pdp=cloudpdp.api.permit.io",
        "cloudpdp.api.permit.io",
        "http://[::1",
    ],
)
def test_an_address_on_another_host_does_not_warn(
    config: PermitConfig, pdp: str, flavour: str
) -> None:
    """Nor does one with no host, or one that cannot be parsed."""
    config.pdp = pdp
    config.proxy_facts_via_pdp = True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = create(config, flavour)
    close(client)

    assert caught == []


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(("action", "shown"), [("always", 2), ("default", 1)])
def test_each_creation_warns_and_the_default_filter_shows_it_once_per_line(
    config: PermitConfig, action: Literal["always", "default"], shown: int, flavour: str
) -> None:
    config.pdp = CLOUD_PDP_URL
    config.proxy_facts_via_pdp = True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter(action)
        for _ in range(2):
            close(create(config, flavour))

    assert len(caught) == shown


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_wait_for_sync_client_does_not_warn_again(config: PermitConfig, flavour: str) -> None:
    config.pdp = CLOUD_PDP_URL
    config.proxy_facts_via_pdp = True
    with pytest.warns(UserWarning, match="^proxy_facts_via_pdp is on"):
        client = create(config, flavour)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with client.wait_for_sync(timeout=1.0) as waiting:
            assert waiting is not client
    close(client)

    assert caught == []


def test_a_subclass_warns_at_the_line_that_created_it(config: PermitConfig) -> None:
    class Subclass(Permit):
        def __init__(self, config: PermitConfig) -> None:
            super().__init__(config)

    config.pdp = CLOUD_PDP_URL
    config.proxy_facts_via_pdp = True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        line = sys._getframe().f_lineno + 1
        client = Subclass(config)
    close(client)

    assert [(w.filename, w.lineno) for w in caught] == [(__file__, line)]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_facts_through_the_cloud_pdps_host_warn_then_ask_for_a_container_pdp(
    pdp_server: HTTPServer, split_config: PermitConfig, cloud_pdp_url: str, flavour: str
) -> None:
    """At the cloud PDP's address, a 404 with a body counts as the cloud PDP's too."""
    split_config.pdp = cloud_pdp_url
    split_config.proxy_facts_via_pdp = True
    pdp_server.expect_request("/facts/users", method="POST").respond_with_data(
        '{"detail": "Not Found"}', status=404, content_type="application/json"
    )

    with (
        pytest.warns(UserWarning, match="^proxy_facts_via_pdp is on") as caught,
        pytest.raises(PermitApiError) as raised,
    ):
        invoke(split_config, flavour, CASES["users.create"].call)

    assert [str(w.message) for w in caught] == [facts_proxied_to_the_cloud_pdp(cloud_pdp_url)]
    message = container_pdp_only("POST /facts/users", cloud_pdp_url, USE_A_CONTAINER_PDP_FOR_FACTS)
    assert type(raised.value) is PermitApiError
    assert str(raised.value) == message
    assert [sent(request) for request, _ in pdp_server.log] == [CASES["users.create"].request]
