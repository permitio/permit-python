"""Offline tests for tenant membership (PER-16678): get_user_tenants().

Each call goes through the async and the blocking client, and the test checks the request
it puts on the wire (method, path, query string, headers and JSON body) and what the
response parses into. Every request is served by a local ``pytest_httpserver`` and the API
context is pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
from operator import attrgetter
from typing import Any, NamedTuple

import pytest
from pydantic.v1 import ValidationError
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit, TenantDetails
from permit.config import PermitConfig
from permit.enforcement.enforcer import Enforcer
from permit.exceptions import PermitConnectionError
from permit.sync import Permit as SyncPermit
from tests.utils import Call, call, sent

FLAVOURS = ["async", "sync"]

# The headers the SDK sets. The wait-for-sync ones are listed so that sending one shows.
HEADERS = ("Authorization", "Content-Type", "X-Wait-Timeout", "X-Timeout-Policy")
JSON_HEADERS: dict[str, str | None] = {
    "Authorization": "Bearer test-token",
    "Content-Type": "application/json",
    "X-Wait-Timeout": None,
    "X-Timeout-Policy": None,
}


class Case(NamedTuple):
    """One SDK call, and the path and JSON body of the one request it must send."""

    call: Call
    path: str
    body: Any


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``permit.<target.path>`` on the async or the blocking client."""
    permit = Permit(config) if flavour == "async" else SyncPermit(config)
    result = attrgetter(target.path)(permit)(*target.args, **target.kwargs)
    if flavour == "async":
        return asyncio.run(result)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


# --- get_user_tenants() -----------------------------------------------------------


USER_TENANTS = "/user-tenants"
PDP_TENANTS = [
    {"key": "t1", "attributes": {"tier": "gold", "region": {"name": "eu"}}},
    {"key": "t2", "attributes": {}},
    {"key": "t3"},
]
ATTRIBUTES = {"dept": "eng", "level": 3}


GET_USER_TENANTS_CASES = {
    "str-user": Case(
        call("get_user_tenants", "alice"),
        USER_TENANTS,
        {"user": {"key": "alice"}, "context": {}},
    ),
    "str-user-context": Case(
        call("get_user_tenants", "alice", {"region": "eu"}),
        USER_TENANTS,
        {"user": {"key": "alice"}, "context": {"region": "eu"}},
    ),
    "dict-user-attributes": Case(
        call("get_user_tenants", {"key": "alice", "attributes": ATTRIBUTES}),
        USER_TENANTS,
        {"user": {"key": "alice", "attributes": ATTRIBUTES}, "context": {}},
    ),
    "dict-user-attributes-context": Case(
        call(
            "get_user_tenants",
            user={"key": "alice", "attributes": ATTRIBUTES},
            context={"region": "eu"},
        ),
        USER_TENANTS,
        {"user": {"key": "alice", "attributes": ATTRIBUTES}, "context": {"region": "eu"}},
    ),
    "dict-user-aliases": Case(
        call(
            "get_user_tenants",
            {"key": "alice", "firstName": "Alice", "lastName": "Smith", "email": "a@example.com"},
        ),
        USER_TENANTS,
        {
            "user": {
                "key": "alice",
                "first_name": "Alice",
                "last_name": "Smith",
                "email": "a@example.com",
            },
            "context": {},
        },
    ),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", GET_USER_TENANTS_CASES.values(), ids=GET_USER_TENANTS_CASES.keys())
def test_get_user_tenants_posts_the_user_and_context_to_the_pdp(
    httpserver: HTTPServer, config: PermitConfig, case: Case, flavour: str
) -> None:
    httpserver.expect_request(case.path, method="POST").respond_with_json(PDP_TENANTS)

    invoke(config, flavour, case.call)

    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": "POST", "path": case.path, "query": [], "body": case.body}
    ]
    assert [sent_headers(request) for request, _ in httpserver.log] == [JSON_HEADERS]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_get_user_tenants_returns_the_pdp_tenants_as_tenant_details(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    """A tenant the PDP sends without attributes gets an empty dict."""
    httpserver.expect_request(USER_TENANTS, method="POST").respond_with_json(PDP_TENANTS)

    result = invoke(config, flavour, call("get_user_tenants", "alice"))

    assert type(result) is list
    assert [type(tenant) for tenant in result] == [TenantDetails] * 3
    assert result == [
        TenantDetails(key="t1", attributes={"tier": "gold", "region": {"name": "eu"}}),
        TenantDetails(key="t2", attributes={}),
        TenantDetails(key="t3", attributes={}),
    ]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_get_user_tenants_returns_an_empty_list_for_a_user_in_no_tenant(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    httpserver.expect_request(USER_TENANTS, method="POST").respond_with_json([])

    assert invoke(config, flavour, call("get_user_tenants", "nobody")) == []


async def test_get_user_tenants_merges_the_query_context_over_the_context_store(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    enforcer = Enforcer(config)
    enforcer.context_store.add({"region": "eu", "flags": {"a": 1}})
    httpserver.expect_request(USER_TENANTS, method="POST").respond_with_json([])

    await enforcer.get_user_tenants("alice", {"flags": {"b": 2}})

    assert [sent(request)["body"] for request, _ in httpserver.log] == [
        {"user": {"key": "alice"}, "context": {"region": "eu", "flags": {"a": 1, "b": 2}}}
    ]
    assert enforcer.context_store.get_derived_context({}) == {"region": "eu", "flags": {"a": 1}}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("body", "content_type"),
    [("", None), ('{"detail": "Not Found"}', "application/json")],
    ids=["empty", "json"],
)
def test_a_pdp_answering_404_raises_a_connection_error_that_asks_for_a_container_pdp(
    httpserver: HTTPServer,
    config: PermitConfig,
    body: str,
    content_type: str | None,
    flavour: str,
) -> None:
    """The cloud PDP does not serve /user-tenants and answers 404 for it."""
    httpserver.expect_request(USER_TENANTS, method="POST").respond_with_data(
        body, status=404, content_type=content_type
    )

    with pytest.raises(PermitConnectionError) as raised:
        invoke(config, flavour, call("get_user_tenants", "alice"))

    message = str(raised.value)
    assert "got status code 404 from the PDP" in message
    assert "only the container PDP serves /user-tenants, and the cloud PDP does not" in message
    assert raised.value.original_error is None
    assert len(httpserver.log) == 1


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("status", [401, 500])
@pytest.mark.parametrize(
    ("pdp_path", "target"),
    [
        (USER_TENANTS, call("get_user_tenants", "alice")),
        ("/user-permissions", call("get_user_permissions", "alice")),
    ],
    ids=["get_user_tenants", "get_user_permissions"],
)
def test_another_pdp_error_status_raises_a_connection_error_as_get_user_permissions_does(
    *,
    httpserver: HTTPServer,
    config: PermitConfig,
    pdp_path: str,
    target: Call,
    status: int,
    flavour: str,
) -> None:
    httpserver.expect_request(pdp_path, method="POST").respond_with_json(
        {"detail": "boom"}, status=status
    )

    with pytest.raises(PermitConnectionError) as raised:
        invoke(config, flavour, target)

    message = str(raised.value)
    assert f"got an unexpected status code: {status}" in message
    assert "container PDP serves" not in message
    assert raised.value.original_error is None
    assert len(httpserver.log) == 1


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_get_user_tenants_puts_the_pdp_error_body_in_the_error(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    httpserver.expect_request(USER_TENANTS, method="POST").respond_with_json(
        {"detail": "policy engine unavailable"}, status=500
    )

    with pytest.raises(PermitConnectionError) as raised:
        invoke(config, flavour, call("get_user_tenants", "alice"))

    assert "Response body: {'detail': 'policy engine unavailable'}" in str(raised.value)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_get_user_tenants_raises_a_connection_error_when_the_pdp_is_unreachable(
    config: PermitConfig, flavour: str
) -> None:
    config.pdp = "http://localhost:1"

    with pytest.raises(
        PermitConnectionError, match="cannot connect to the PDP container"
    ) as raised:
        invoke(config, flavour, call("get_user_tenants", "alice"))

    assert raised.value.original_error is not None


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    "user", [{"attributes": ATTRIBUTES}, {"key": None}], ids=["no-key", "null-key"]
)
def test_get_user_tenants_rejects_a_user_without_a_key_before_sending(
    httpserver: HTTPServer, config: PermitConfig, user: dict[str, Any], flavour: str
) -> None:
    with pytest.raises(ValidationError):
        invoke(config, flavour, call("get_user_tenants", user))

    assert httpserver.log == []


def test_tenant_details_gives_each_tenant_its_own_attributes() -> None:
    first = TenantDetails(key="t1")
    first.attributes["tier"] = "gold"

    assert TenantDetails(key="t2").attributes == {}
