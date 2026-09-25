"""Offline tests for SimpleHttpClient request-body serialization.

These drive the real aiohttp client against a local pytest_httpserver and assert on the
exact JSON body that reaches the wire. No API key, no PDP and no network are involved.

Three behaviours are pinned here:

1. Raw ``dict``/``list`` bodies go through the same encoder as pydantic models, so a
   nested ``datetime``/``UUID``/``Enum``/``Decimal`` no longer blows up inside aiohttp.
2. Only ``exclude_unset`` is applied. A field that was never set is omitted; a field
   explicitly set to ``None`` is transmitted as JSON ``null`` so the API can tell
   "leave this alone" apart from "clear this value".
3. Every value a caller sets reaches the wire with its JSON type, under either
   pydantic major.
"""

import datetime
import json
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List
from uuid import UUID

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Response

from permit.api.base import SimpleHttpClient
from permit.api.models import (
    AttributeType,
    ConditionSetCreate,
    ConditionSetType,
    ElementsUserInviteCreate,
    ResourceAttributeCreate,
    ResourceInstanceCreate,
    ResourceInstanceUpdate,
    RoleAssignmentCreate,
    TenantCreate,
    UserCreate,
    UserInviteStatus,
    UserUpdate,
)
from permit.utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel
else:
    from pydantic.v1 import BaseModel  # type: ignore[assignment]

FIXED_DATETIME = datetime.datetime(2024, 3, 1, 12, 30, 45)
FIXED_UUID = UUID("11111111-2222-3333-4444-555555555555")


class Ack(BaseModel):
    """Minimal response model -- these tests only care about the request body."""

    ok: bool


class Tier(str, Enum):
    PRO = "pro"


@pytest.fixture
def client(httpserver: HTTPServer) -> SimpleHttpClient:
    return SimpleHttpClient(
        {"headers": {"Content-Type": "application/json"}},
        base_url=httpserver.url_for("/v2"),
    )


@pytest.fixture
def captured(httpserver: HTTPServer) -> list:
    """Register a catch-all handler that records every received JSON body."""
    bodies: list = []

    def handler(request):
        bodies.append(request.get_json())
        return Response('{"ok": true}', status=200, content_type="application/json")

    httpserver.expect_request("/v2/echo").respond_with_handler(handler)
    return bodies


async def test_explicitly_set_none_is_transmitted_as_null(client: SimpleHttpClient, captured: list):
    """An explicit ``email=None`` must reach the API as ``null``, not be dropped.

    Before the fix ``exclude_none=True`` removed it, so ``users.update()`` silently
    no-opped instead of clearing the email.
    """
    await client.patch("/echo", model=Ack, json=UserUpdate(email=None, first_name="Jane"))

    assert captured == [{"email": None, "first_name": "Jane"}]


async def test_never_set_field_is_omitted(client: SimpleHttpClient, captured: list):
    """``exclude_unset`` still applies: untouched fields never appear in the body."""
    await client.patch("/echo", model=Ack, json=UserUpdate(first_name="Jane"))

    assert captured == [{"first_name": "Jane"}]
    assert "email" not in captured[0]
    assert "last_name" not in captured[0]


async def test_null_inside_attributes_dict_is_preserved(client: SimpleHttpClient, captured: list):
    """A ``null`` the caller put inside an ``attributes`` dict must survive.

    ``exclude_none`` recursed into plain dicts, so an attribute explicitly set to null
    was stripped instead of being stored as null.
    """
    await client.patch(
        "/echo",
        model=Ack,
        json=UserUpdate(attributes={"department": None, "age": 30, "nested": {"expired": None}}),
    )

    assert captured == [{"attributes": {"department": None, "age": 30, "nested": {"expired": None}}}]


async def test_attributes_set_to_null_wholesale(client: SimpleHttpClient, captured: list):
    """Clearing the whole attributes bag is expressible as ``attributes=None``.

    ``attributes`` defaults to ``{}``, so ``exclude_none`` made an explicit ``None``
    indistinguishable from never touching the field at all.
    """
    await client.patch("/echo", model=Ack, json=ResourceInstanceUpdate(attributes=None))

    assert captured == [{"attributes": None}]


async def test_raw_dict_with_datetime_uuid_and_enum_is_encoded(client: SimpleHttpClient, captured: list):
    """A raw dict body is now encoded.

    Before the fix ``_prepare_json`` returned dicts unchanged, and aiohttp raised
    ``TypeError: Object of type datetime is not JSON serializable``.
    """
    await client.put(
        "/echo",
        model=Ack,
        json={
            "key": "user-1",
            "attributes": {
                "created": FIXED_DATETIME,
                "id": FIXED_UUID,
                "tier": Tier.PRO,
                "balance": Decimal("10.5"),
                "cleared": None,
            },
        },
    )

    assert captured == [
        {
            "key": "user-1",
            "attributes": {
                "created": "2024-03-01T12:30:45",
                "id": "11111111-2222-3333-4444-555555555555",
                "tier": "pro",
                "balance": 10.5,
                "cleared": None,
            },
        }
    ]


async def test_raw_dict_keys_are_never_dropped(client: SimpleHttpClient, captured: list):
    """Encoding a dict must not remove keys -- the API schemas use ``Extra.forbid``,
    and a silently dropped key is how the original ``exclude_none`` bug manifested."""
    body = {"key": "user-1", "email": None, "first_name": None}

    await client.post("/echo", model=Ack, json=body)

    assert captured == [body]


async def test_list_body_encodes_each_item(client: SimpleHttpClient, captured: list):
    """A list body is handled, mixing models and raw dicts."""
    await client.post(
        "/echo",
        model=Ack,
        json=[
            UserCreate(key="a", email=None),
            {"key": "b", "created": FIXED_DATETIME},
        ],
    )

    assert captured == [
        [
            {"key": "a", "email": None},
            {"key": "b", "created": "2024-03-01T12:30:45"},
        ]
    ]


async def test_no_body_stays_absent(client: SimpleHttpClient, httpserver: HTTPServer):
    """``json=None`` must not turn into a ``null`` body."""
    seen: list = []

    def handler(request):
        seen.append(request.get_data())
        return Response('{"ok": true}', status=200, content_type="application/json")

    httpserver.expect_request("/v2/nobody").respond_with_handler(handler)

    await client.delete("/nobody", model=Ack, json=None)

    assert seen == [b""]


async def test_role_assignment_body_unchanged(client: SimpleHttpClient, captured: list):
    """users.assign_role routes a model through this path; its body must not grow keys.

    The backend's ``UserRoleCreate.tenant``/``resource_instance`` are nullable, but an
    unset ``resource_instance`` still has to stay out of the body -- the backend rejects
    an assignment that carries neither, and the root validator only sees what we send.
    """
    assignment = RoleAssignmentCreate(role="admin", tenant="stripe-inc", user="jane")
    await client.post("/echo", model=Ack, json=assignment.copy(exclude={"user"}))

    assert captured == [{"role": "admin", "tenant": "stripe-inc"}]


UNICODE_NAME = "Ünïcødé ✓ 名前 🔐 مرحبا"
MIXED_TEXT = "emoji ✅🚀 · combining e\u0301 vs \u00e9 · rtl \u202eabc\u202c · tab\tend"


def hostile_attributes() -> Dict[str, Any]:
    """Legal attribute values a lossy encoder would change: a bool beside ints, a whole float,
    unicode with bidi controls, keys with separators, empty containers, nesting and nulls."""
    return {
        "unicode": UNICODE_NAME,
        "mixed": MIXED_TEXT,
        "empty_string": "",
        "true": True,
        "false": False,
        "zero": 0,
        "one": 1,
        "negative": -42,
        "max_safe_int": 9007199254740991,
        "pi": 3.141592653589793,
        "whole_float": 2.0,
        "iso_datetime": "2024-01-31T23:59:59.123456+05:30",
        "empty_object": {},
        "empty_list": [],
        "mixed_list": [1, "two", 3.0, True, None],
        "key.with.dots": "dots",
        "key-with-dashes": "dashes",
        "cleared": None,
        "nested": {
            "level2": {"level3": [{"flag": False, "cleared": None}, {"name": UNICODE_NAME, "count": 1}]},
            "matrix": [[1, 2], [3, 4]],
        },
    }


def user_body() -> Dict[str, Any]:
    return {
        "key": "user-1",
        "email": "user-1@example.com",
        "first_name": UNICODE_NAME,
        "last_name": "O'Brien-Núñez 🙂",
        "attributes": hostile_attributes(),
    }


def tenant_body() -> Dict[str, Any]:
    return {"key": "tenant-1", "name": UNICODE_NAME, "description": MIXED_TEXT, "attributes": hostile_attributes()}


def resource_instance_body() -> Dict[str, Any]:
    return {"key": "doc-1", "resource": "document", "tenant": "tenant-1", "attributes": hostile_attributes()}


# Each model is built from its own copy of the payload, so a serializer that edited the
# caller's dicts in place could not also edit the expected body.
WIRE_BODIES: List[Any] = [
    pytest.param(UserCreate(**user_body()), user_body(), id="UserCreate"),
    pytest.param(TenantCreate(**tenant_body()), tenant_body(), id="TenantCreate"),
    pytest.param(
        ResourceInstanceCreate(**resource_instance_body()), resource_instance_body(), id="ResourceInstanceCreate"
    ),
    pytest.param(
        ResourceAttributeCreate(key="level", type=AttributeType.number, description=MIXED_TEXT),
        {"key": "level", "type": "number", "description": MIXED_TEXT},
        id="ResourceAttributeCreate",
    ),
    pytest.param(
        ConditionSetCreate(
            key="gold-users",
            name=UNICODE_NAME,
            type=ConditionSetType.userset,
            conditions={
                "allOf": [{"user.attributes.tier": {"equals": "gold"}}, {"user.attributes.true": {"equals": True}}]
            },
        ),
        {
            "key": "gold-users",
            "name": UNICODE_NAME,
            "type": "userset",
            "conditions": {
                "allOf": [{"user.attributes.tier": {"equals": "gold"}}, {"user.attributes.true": {"equals": True}}]
            },
        },
        id="ConditionSetCreate",
    ),
    pytest.param(
        ElementsUserInviteCreate(
            key="invite@example.com",
            status=UserInviteStatus.pending,
            email="invite@example.com",
            first_name="Ada",
            last_name=UNICODE_NAME,
            role_id=FIXED_UUID,
            tenant_id=FIXED_UUID,
            resource_instance_id=FIXED_UUID,
        ),
        {
            "key": "invite@example.com",
            "status": "pending",
            "email": "invite@example.com",
            "first_name": "Ada",
            "last_name": UNICODE_NAME,
            "role_id": "11111111-2222-3333-4444-555555555555",
            "tenant_id": "11111111-2222-3333-4444-555555555555",
            "resource_instance_id": "11111111-2222-3333-4444-555555555555",
        },
        id="ElementsUserInviteCreate",
    ),
]


@pytest.mark.parametrize(("body", "expected"), WIRE_BODIES)
async def test_request_body_reaches_the_wire_exactly_as_given(
    client: SimpleHttpClient, captured: list, body: Any, expected: Dict[str, Any]
):
    """Every value arrives with its JSON type and every key survives, nulls included.

    Each expected body is a literal and CI runs this file under both pydantic majors, so a
    major that serialized any of these bodies differently would fail here.
    """
    await client.post("/echo", model=Ack, json=body)

    assert captured == [expected]
    # == takes True for 1 and 2.0 for 2. Their JSON text tells them apart.
    assert json.dumps(captured, sort_keys=True) == json.dumps([expected], sort_keys=True)
