"""Offline regression tests for the enforcement layer (group B).

Every request is served by a local ``pytest_httpserver``: no network, no API
key and no PDP container. The assertions are on the exact JSON body the SDK
puts on the wire, because that body is what decides an authorization outcome.
"""

import json
from typing import Any, Dict, List

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

from permit.config import PermitConfig
from permit.enforcement.enforcer import Enforcer
from permit.enforcement.interfaces import AuthorizedUsersResult, UserInput


@pytest.fixture
def pdp_url(httpserver: HTTPServer) -> str:
    return httpserver.url_for("").rstrip("/")


@pytest.fixture
def enforcer(pdp_url: str) -> Enforcer:
    return Enforcer(
        PermitConfig(
            token="offline-test-token",
            pdp=pdp_url,
            api_url="http://localhost:1",
            log={"level": "debug", "enable": False},
        )
    )


def _recorder(bodies: List[Any], payload: Any):
    def handler(request: Request) -> Response:
        bodies.append(json.loads(request.get_data()))
        return Response(json.dumps(payload), content_type="application/json")

    return handler


# --- bug 1: unguarded `from pydantic import parse_obj_as` --------------------


@pytest.mark.asyncio
async def test_authorized_users_parses_pdp_response(httpserver: HTTPServer, enforcer: Enforcer):
    """Before the fix this raised TypeError under pydantic v2.

    ``AuthorizedUsersResult`` is a pydantic v1 model, so the v2 ``parse_obj_as``
    shim called ``BaseModel.validate(cls, obj)`` on it:
    "BaseModel.validate() takes 2 positional arguments but 3 were given".
    """
    bodies: List[Any] = []
    pdp_response = {
        "resource": "document:readme",
        "tenant": "default",
        "users": {
            "user_a": [
                {
                    "user": "user_a",
                    "tenant": "default",
                    "resource": "document:readme",
                    "role": "editor",
                }
            ]
        },
    }
    httpserver.expect_request("/authorized_users", method="POST").respond_with_handler(_recorder(bodies, pdp_response))

    result = await enforcer.authorized_users("read", "document:readme", {"attr": 1})

    assert isinstance(result, AuthorizedUsersResult)
    assert result.resource == "document:readme"
    assert result.tenant == "default"
    assert result.users["user_a"][0].role == "editor"
    assert bodies == [
        {
            "action": "read",
            "resource": {
                "type": "document",
                "key": "readme",
                "tenant": "default",
                "context": {"tenant": "default"},
            },
            "context": {"attr": 1},
        }
    ]


# --- bug 2: context dropped by bulk_check / filter_objects -------------------


@pytest.mark.asyncio
async def test_bulk_check_sends_per_check_context(httpserver: HTTPServer, enforcer: Enforcer):
    """A per-check ``context`` must reach the wire, not be silently discarded."""
    bodies: List[Any] = []
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_handler(
        _recorder(bodies, {"allow": [{"allow": True}, {"allow": False}]})
    )

    decisions = await enforcer.bulk_check(
        [
            {
                "user": "user_a",
                "action": "read",
                "resource": "document:a",
                "context": {"ip": "10.0.0.1"},
            },
            {
                "user": "user_b",
                "action": "read",
                "resource": "document:b",
                "context": None,
            },
        ]
    )

    assert decisions == [True, False]
    assert [entry["context"] for entry in bodies[0]] == [{"ip": "10.0.0.1"}, {}]


@pytest.mark.asyncio
async def test_bulk_check_merges_per_check_context_over_method_context(httpserver: HTTPServer, enforcer: Enforcer):
    """Precedence: per-check context wins over the method-level context."""
    bodies: List[Any] = []
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_handler(
        _recorder(bodies, {"allow": [{"allow": True}]})
    )

    await enforcer.bulk_check(
        [
            {
                "user": "user_a",
                "action": "read",
                "resource": "document:a",
                "context": {"region": "eu", "nested": {"b": 2}},
            }
        ],
        context={"region": "us", "source": "api", "nested": {"a": 1}},
    )

    assert bodies[0][0]["context"] == {
        "region": "eu",
        "source": "api",
        "nested": {"a": 1, "b": 2},
    }


@pytest.mark.asyncio
async def test_bulk_check_uses_method_context_when_check_has_none(httpserver: HTTPServer, enforcer: Enforcer):
    bodies: List[Any] = []
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_handler(
        _recorder(bodies, {"allow": [{"allow": True}]})
    )

    await enforcer.bulk_check(
        [{"user": "user_a", "action": "read", "resource": "document:a", "context": None}],
        context={"region": "us"},
    )

    assert bodies[0][0]["context"] == {"region": "us"}


@pytest.mark.asyncio
async def test_filter_objects_forwards_caller_context(httpserver: HTTPServer, enforcer: Enforcer):
    """Before the fix every check went out with ``"context": {}``.

    A context-dependent ABAC policy therefore evaluated against an empty
    context and could return the wrong subset.
    """
    bodies: List[Any] = []
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_handler(
        _recorder(bodies, {"allow": [{"allow": True}, {"allow": False}]})
    )

    resources: List[Dict[str, Any]] = [
        {"type": "document", "key": "a", "tenant": "t1", "attributes": {"owner": "user_a"}},
        {"type": "document", "key": "b", "tenant": "t1", "attributes": {"owner": "user_b"}},
    ]
    allowed = await enforcer.filter_objects("user_a", "read", {"location": "eu", "mfa": True}, resources)

    assert allowed == [resources[0]]
    assert [entry["context"] for entry in bodies[0]] == [
        {"location": "eu", "mfa": True},
        {"location": "eu", "mfa": True},
    ]


@pytest.mark.asyncio
async def test_filter_objects_keeps_per_resource_context_on_the_resource(httpserver: HTTPServer, enforcer: Enforcer):
    """A resource-level ``context`` stays on the resource, not on the query."""
    bodies: List[Any] = []
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_handler(
        _recorder(bodies, {"allow": [{"allow": True}]})
    )

    await enforcer.filter_objects(
        "user_a",
        "read",
        {"location": "eu"},
        [{"type": "document", "key": "a", "tenant": "t1", "context": {"branch": "main"}}],
    )

    entry = bodies[0][0]
    assert entry["context"] == {"location": "eu"}
    assert entry["resource"]["context"] == {"branch": "main", "tenant": "t1"}


# --- bug 3: snake_case user fields silently dropped --------------------------


def test_user_input_accepts_snake_case_and_alias():
    assert UserInput(key="u1", first_name="John", last_name="Doe", email="a@b.c").dict(exclude_unset=True) == {
        "key": "u1",
        "first_name": "John",
        "last_name": "Doe",
        "email": "a@b.c",
    }
    assert UserInput(key="u1", firstName="John", lastName="Doe").dict(exclude_unset=True) == {
        "key": "u1",
        "first_name": "John",
        "last_name": "Doe",
    }


@pytest.mark.asyncio
async def test_check_sends_snake_case_user_fields(httpserver: HTTPServer, enforcer: Enforcer):
    """The PDP reads ``first_name``/``last_name``; both spellings must reach it."""
    bodies: List[Any] = []
    httpserver.expect_request("/allowed", method="POST").respond_with_handler(_recorder(bodies, {"allow": True}))

    decision = await enforcer.check(
        {"key": "u1", "first_name": "John", "last_name": "Doe", "attributes": {"tier": "gold"}},
        "read",
        "document:a",
    )

    assert decision is True
    assert bodies[0]["user"] == {
        "key": "u1",
        "first_name": "John",
        "last_name": "Doe",
        "attributes": {"tier": "gold"},
    }


@pytest.mark.asyncio
async def test_bulk_check_sends_snake_case_user_fields(httpserver: HTTPServer, enforcer: Enforcer):
    bodies: List[Any] = []
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_handler(
        _recorder(bodies, {"allow": [{"allow": True}]})
    )

    await enforcer.bulk_check(
        [
            {
                "user": {"key": "u1", "first_name": "John"},
                "action": "read",
                "resource": "document:a",
                "context": None,
            }
        ]
    )

    assert bodies[0][0]["user"] == {"key": "u1", "first_name": "John"}
