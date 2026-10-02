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
from typing import Any, Literal, NamedTuple

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import ErrorCode, Permit, PermitConnectionError
from permit.config import PermitConfig
from permit.exceptions import PermitApiError, PermitNotFoundError
from permit.sync import Permit as SyncPermit
from tests.utils import Call, call, sent

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


class FactsCase(NamedTuple):
    """A facts method's call, and the one request it sends to the PDP's /facts routes."""

    call: Call
    method: str
    path: str
    query: list[tuple[str, str]]
    body: Any


USER = {"key": "alice"}
TENANT = {"key": "t1", "name": "T1"}
ASSIGNMENT = {"user": "alice", "role": "viewer", "tenant": "t1"}
INSTANCE = {"key": "doc-1", "resource": "document", "tenant": "t1"}
TUPLE = {"subject": "folder:f1", "relation": "parent", "object": "document:doc-1"}
PAGE = [("page", "1"), ("per_page", "100")]

# Facts methods of each API class, over each HTTP verb. The API coverage report fails on a
# request that neither the PDP's spec nor an `sdk_only` entry of
# .github/scripts/api_coverage_allowlist.json accounts for, so these send only such requests.
FACTS_CASES = {
    "users.create": FactsCase(call("api.users.create", USER), "POST", "/facts/users", [], USER),
    "users.update": FactsCase(
        call("api.users.update", "alice", {"first_name": "Alice"}),
        "PATCH",
        "/facts/users/alice",
        [],
        {"first_name": "Alice"},
    ),
    "users.assign_role": FactsCase(
        call("api.users.assign_role", ASSIGNMENT),
        "POST",
        "/facts/users/alice/roles",
        [],
        {"role": "viewer", "tenant": "t1"},
    ),
    "users.bulk_create": FactsCase(
        call("api.users.bulk_create", [USER]),
        "POST",
        "/facts/bulk/users",
        [],
        {"operations": [USER]},
    ),
    "tenants.create": FactsCase(
        call("api.tenants.create", TENANT), "POST", "/facts/tenants", [], TENANT
    ),
    "tenants.delete": FactsCase(
        call("api.tenants.delete", "t1"), "DELETE", "/facts/tenants/t1", [], None
    ),
    "tenants.delete_tenant_user": FactsCase(
        call("api.tenants.delete_tenant_user", "t1", "alice"),
        "DELETE",
        "/facts/tenants/t1/users/alice",
        [],
        None,
    ),
    "tenants.bulk_create": FactsCase(
        call("api.tenants.bulk_create", [TENANT]),
        "POST",
        "/facts/bulk/tenants",
        [],
        {"operations": [TENANT]},
    ),
    "role_assignments.assign": FactsCase(
        call("api.role_assignments.assign", ASSIGNMENT),
        "POST",
        "/facts/role_assignments",
        [],
        ASSIGNMENT,
    ),
    "role_assignments.list_detailed": FactsCase(
        call("api.role_assignments.list_detailed", user_key="alice"),
        "GET",
        "/facts/role_assignments/detailed",
        [*PAGE, ("user", "alice")],
        None,
    ),
    "resource_instances.create": FactsCase(
        call("api.resource_instances.create", INSTANCE),
        "POST",
        "/facts/resource_instances",
        [],
        INSTANCE,
    ),
    "resource_instances.bulk_replace": FactsCase(
        call("api.resource_instances.bulk_replace", [INSTANCE]),
        "PUT",
        "/facts/bulk/resource_instances",
        [],
        {"operations": [INSTANCE]},
    ),
    "relationship_tuples.create": FactsCase(
        call("api.relationship_tuples.create", TUPLE),
        "POST",
        "/facts/relationship_tuples",
        [],
        TUPLE,
    ),
    "relationship_tuples.list_detailed": FactsCase(
        call("api.relationship_tuples.list_detailed"),
        "GET",
        "/facts/relationship_tuples/detailed",
        PAGE,
        None,
    ),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", FACTS_CASES.values(), ids=FACTS_CASES.keys())
def test_a_facts_method_raises_the_cloud_pdp_404_as_an_api_error_that_asks_for_a_container_pdp(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    case: FactsCase,
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
    assert [sent(request) for request, _ in pdp_server.log] == [
        {"method": case.method, "path": case.path, "query": case.query, "body": case.body}
    ]
    assert [sent_headers(request) for request, _ in pdp_server.log] == [JSON_HEADERS]
    assert httpserver.log == []


NOT_FOUND_DETAILS = {
    "id": "request-1",
    "title": "The requested data was not found",
    "error_code": "NOT_FOUND",
    "message": "Tenant with key 't1' was not found.",
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    "case",
    [FACTS_CASES["tenants.delete"], FACTS_CASES["users.update"]],
    ids=["tenants.delete", "users.update"],
)
def test_the_apis_404_through_a_container_pdp_keeps_its_not_found_error(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    case: FactsCase,
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
        "Tenant with key 't1' was not found.\n"
        "For more information: https://permit-io.slack.com/ssb/redirect (Request ID: request-1)"
    )
    assert raised.value.details == NOT_FOUND_DETAILS
    assert len(pdp_server.log) == 1
    assert httpserver.log == []


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("proxy_facts_via_pdp", "path", "target"),
    [
        (True, "/facts/users", call("api.users.create", USER)),
        (False, "/local/role_assignments", call("pdp_api.role_assignments.list")),
    ],
    ids=["facts", "pdp_api"],
)
def test_a_container_pdps_own_404_keeps_the_api_error_it_raised(
    *,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    proxy_facts_via_pdp: bool,
    path: str,
    target: Call,
    flavour: str,
) -> None:
    """A container PDP answers a route it does not serve with a JSON 404."""
    split_config.proxy_facts_via_pdp = proxy_facts_via_pdp
    pdp_server.expect_request(path).respond_with_json({"detail": "Not Found"}, status=404)

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, target)

    assert type(raised.value) is PermitApiError
    assert str(raised.value) == "404 API Error: {'detail': 'Not Found'}"
    assert raised.value.details == {"detail": "Not Found"}


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_apis_empty_404_keeps_its_api_error_with_proxy_facts_via_pdp_off(
    httpserver: HTTPServer, pdp_server: HTTPServer, split_config: PermitConfig, flavour: str
) -> None:
    """Only the PDP's container-only routes read an empty 404 as the cloud PDP's."""
    path = "/v2/facts/test-project/test-env/users"
    httpserver.expect_request(path, method="POST").respond_with_data("", status=404)

    with pytest.raises(PermitApiError) as raised:
        invoke(split_config, flavour, call("api.users.create", USER))

    assert type(raised.value) is PermitApiError
    assert str(raised.value) == "404 API Error: {'details': ''}"
    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": "POST", "path": path, "query": [], "body": USER}
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
            "query": [*PAGE, ("user", "alice")],
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


# With proxy_facts_via_pdp on, every public method of these APIs sends its request to the
# PDP's /facts routes, except tenants.create_user() and its deprecated alias add_user(),
# which always go to the Permit REST API.
FACTS_APIS = ("users", "tenants", "role_assignments", "resource_instances", "relationship_tuples")
API_ONLY = ("api.tenants.create_user", "api.tenants.add_user")
FACTS_METHODS = (
    *(
        f"api.users.{name}"
        for name in (
            "assign_role",
            "bulk_create",
            "bulk_delete",
            "bulk_replace",
            "create",
            "delete",
            "get",
            "get_assigned_roles",
            "get_by_id",
            "get_by_key",
            "list",
            "sync",
            "unassign_role",
            "update",
        )
    ),
    *(
        f"api.tenants.{name}"
        for name in (
            "bulk_create",
            "bulk_delete",
            "create",
            "delete",
            "delete_tenant_user",
            "get",
            "get_by_id",
            "get_by_key",
            "list",
            "list_tenant_users",
            "update",
        )
    ),
    *(
        f"api.role_assignments.{name}"
        for name in ("assign", "bulk_assign", "bulk_unassign", "list", "list_detailed", "unassign")
    ),
    *(
        f"api.resource_instances.{name}"
        for name in (
            "bulk_delete",
            "bulk_replace",
            "create",
            "delete",
            "get",
            "get_by_id",
            "get_by_key",
            "list",
            "list_detailed",
            "update",
        )
    ),
    *(
        f"api.relationship_tuples.{name}"
        for name in ("bulk_create", "bulk_delete", "create", "delete", "list", "list_detailed")
    ),
)
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


def test_the_facts_methods_are_every_public_method_of_the_facts_apis_but_create_user(
    client: Permit,
) -> None:
    public = {
        f"api.{api}.{name}"
        for api in FACTS_APIS
        for name in dir(getattr(client.api, api))
        if not name.startswith("_") and callable(getattr(getattr(client.api, api), name))
    }

    assert sorted(public - set(API_ONLY)) == sorted(FACTS_METHODS)


@pytest.mark.parametrize("path", NOTES.keys())
def test_a_container_pdp_only_method_says_so_in_its_docstring(client: Permit, path: str) -> None:
    assert NOTES[path] in docstring(client, path)


@pytest.mark.parametrize("path", API_ONLY)
def test_a_facts_api_method_that_always_goes_to_the_api_does_not_say_container_pdp_only(
    client: Permit, path: str
) -> None:
    assert "Container PDP only" not in docstring(client, path)


# --- the warning at creation ----------------------------------------------------------


CLOUD_PDP_URL = f"https://{CLOUD_PDP_HOST}"


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
        invoke(split_config, flavour, call("api.users.create", USER))

    assert [str(w.message) for w in caught] == [facts_proxied_to_the_cloud_pdp(cloud_pdp_url)]
    message = container_pdp_only("POST /facts/users", cloud_pdp_url, USE_A_CONTAINER_PDP_FOR_FACTS)
    assert type(raised.value) is PermitApiError
    assert str(raised.value) == message
    assert [sent(request) for request, _ in pdp_server.log] == [
        {"method": "POST", "path": "/facts/users", "query": [], "body": USER}
    ]
