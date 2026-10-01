"""Offline tests for the context of get_user_permissions() (PER-16337).

``get_user_permissions(..., context=...)`` is called on the Enforcer and through the async
and the blocking client, and the tests check the exact bytes of the request body it sends to
the PDP's ``/user-permissions``. Without a context the body is byte for byte what 3.0 sent:
no ``context`` key, whatever the context store holds. With one, the body ends with the
context merged over the context store's base context, as ``check()`` merges it. Every
request is served by a local ``pytest_httpserver``, so no API key or PDP is needed.
"""

import asyncio
import inspect
from operator import attrgetter
from typing import Any, NamedTuple

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.config import PermitConfig
from permit.enforcement.enforcer import Enforcer
from permit.sync import Permit as SyncPermit
from tests.utils import Call, call

FLAVOURS = ["async", "sync"]
USER_PERMISSIONS = "/user-permissions"
HEADERS: dict[str, str | None] = {
    "Authorization": "Bearer test-token",
    "Content-Type": "application/json",
}
PERMISSIONS = {"__tenant:t1": {"tenant": {"key": "t1"}, "permissions": ["document:read"]}}
STORE = {"region": "eu", "flags": {"a": 1}}


class Case(NamedTuple):
    """One get_user_permissions() call and the exact request body it must send."""

    call: Call
    body: bytes


# Bodies without a context, as permit 3.0 sends them: json.dumps of the user and the
# three filters, in that order, nulls included.
WITHOUT_CONTEXT = {
    "user-key": Case(
        call("get_user_permissions", "alice"),
        b'{"user": {"key": "alice"}, "tenants": null, "resources": null, "resource_types": null}',
    ),
    "user-dict-and-filters": Case(
        call(
            "get_user_permissions",
            {"key": "alice", "attributes": {"dept": "eng"}},
            ["t1"],
            ["document:readme"],
            ["document"],
        ),
        b'{"user": {"key": "alice", "attributes": {"dept": "eng"}}, "tenants": ["t1"], '
        b'"resources": ["document:readme"], "resource_types": ["document"]}',
    ),
    "context-none": Case(
        call("get_user_permissions", "alice", tenants=["t1"], context=None),
        b'{"user": {"key": "alice"}, "tenants": ["t1"], "resources": null, "resource_types": null}',
    ),
}
WITH_CONTEXT = {
    "context-keyword": Case(
        call("get_user_permissions", "alice", context={"region": "us", "ip": "10.0.0.1"}),
        b'{"user": {"key": "alice"}, "tenants": null, "resources": null, "resource_types": null, '
        b'"context": {"region": "us", "ip": "10.0.0.1"}}',
    ),
    "context-positional-with-filters": Case(
        call("get_user_permissions", "alice", ["t1"], None, ["document"], {"time": 12}),
        b'{"user": {"key": "alice"}, "tenants": ["t1"], "resources": null, '
        b'"resource_types": ["document"], "context": {"time": 12}}',
    ),
    "context-json-types": Case(
        call(
            "get_user_permissions",
            "alice",
            context={"ok": True, "n": 1.5, "none": None, "name": "ré", "list": [1, "a"]},
        ),
        b'{"user": {"key": "alice"}, "tenants": null, "resources": null, "resource_types": null, '
        b'"context": {"ok": true, "n": 1.5, "none": null, "name": "r\\u00e9", "list": [1, "a"]}}',
    ),
    "context-empty": Case(
        call("get_user_permissions", "alice", context={}),
        b'{"user": {"key": "alice"}, "tenants": null, "resources": null, "resource_types": null, '
        b'"context": {}}',
    ),
}


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``permit.<target.path>`` on the async or the blocking client."""
    permit = Permit(config) if flavour == "async" else SyncPermit(config)
    result = attrgetter(target.path)(permit)(*target.args, **target.kwargs)
    if flavour == "async":
        return asyncio.run(result)
    assert not inspect.isawaitable(result)
    return result


def sent_bodies(httpserver: HTTPServer) -> list[bytes]:
    return [request.get_data() for request, _ in httpserver.log]


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    "case",
    [*WITHOUT_CONTEXT.values(), *WITH_CONTEXT.values()],
    ids=[*WITHOUT_CONTEXT.keys(), *WITH_CONTEXT.keys()],
)
def test_get_user_permissions_sends_exactly_this_body(
    httpserver: HTTPServer, config: PermitConfig, case: Case, flavour: str
) -> None:
    httpserver.expect_request(USER_PERMISSIONS, method="POST").respond_with_json(PERMISSIONS)

    result = invoke(config, flavour, case.call)

    assert sent_bodies(httpserver) == [case.body]
    assert [request.path for request, _ in httpserver.log] == [USER_PERMISSIONS]
    assert [request.query_string for request, _ in httpserver.log] == [b""]
    assert [sent_headers(request) for request, _ in httpserver.log] == [HEADERS]
    assert result == PERMISSIONS


@pytest.mark.parametrize("case", WITHOUT_CONTEXT.values(), ids=WITHOUT_CONTEXT.keys())
async def test_without_a_context_the_context_store_is_not_sent(
    httpserver: HTTPServer, config: PermitConfig, case: Case
) -> None:
    """The body stays what 3.0 sent, which never carried the context store's base context."""
    enforcer = Enforcer(config)
    enforcer.context_store.add(STORE)
    httpserver.expect_request(USER_PERMISSIONS, method="POST").respond_with_json(PERMISSIONS)

    await enforcer.get_user_permissions(*case.call.args, **case.call.kwargs)

    assert sent_bodies(httpserver) == [case.body]


@pytest.mark.parametrize(
    ("context", "sent_context"),
    [
        ({"flags": {"b": 2}}, b'{"region": "eu", "flags": {"a": 1, "b": 2}}'),
        ({"region": "us"}, b'{"region": "us", "flags": {"a": 1}}'),
        ({}, b'{"region": "eu", "flags": {"a": 1}}'),
    ],
    ids=["deep-merged", "query-wins", "empty-sends-the-store"],
)
async def test_a_context_is_merged_over_the_context_store_as_check_merges_it(
    httpserver: HTTPServer, config: PermitConfig, context: dict[str, Any], sent_context: bytes
) -> None:
    enforcer = Enforcer(config)
    enforcer.context_store.add(STORE)
    httpserver.expect_request(USER_PERMISSIONS, method="POST").respond_with_json(PERMISSIONS)
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})

    await enforcer.get_user_permissions("alice", context=context)
    await enforcer.check("alice", "read", "document", context)

    (permissions_request, _), (check_request, _) = httpserver.log
    assert permissions_request.get_data() == (
        b'{"user": {"key": "alice"}, "tenants": null, "resources": null, "resource_types": null, '
        b'"context": ' + sent_context + b"}"
    )
    assert check_request.get_data().endswith(b'"context": ' + sent_context + b"}")
    assert enforcer.context_store.get_derived_context({}) == STORE


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_clients_merge_the_context_over_their_context_store(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    httpserver.expect_request(USER_PERMISSIONS, method="POST").respond_with_json(PERMISSIONS)
    context = {"flags": {"b": 2}}

    if flavour == "async":
        permit = Permit(config)
        permit._enforcer.context_store.add(STORE)
        asyncio.run(permit.get_user_permissions("alice", context=context))
    else:
        sync_permit = SyncPermit(config)
        sync_permit._enforcer.context_store.add(STORE)
        sync_permit.get_user_permissions("alice", context=context)

    assert sent_bodies(httpserver) == [
        (
            b'{"user": {"key": "alice"}, "tenants": null, "resources": null, '
            b'"resource_types": null, "context": {"region": "eu", "flags": {"a": 1, "b": 2}}}'
        )
    ]
