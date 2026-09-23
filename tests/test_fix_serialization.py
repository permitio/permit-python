"""Offline tests for SimpleHttpClient request-body serialization.

These drive the real aiohttp client against a local pytest_httpserver and assert on the
exact JSON body that reaches the wire. No API key, no PDP and no network are involved.

Two behaviours are pinned here:

1. Raw ``dict``/``list`` bodies go through the same encoder as pydantic models, so a
   nested ``datetime``/``UUID``/``Enum``/``Decimal`` no longer blows up inside aiohttp.
2. Only ``exclude_unset`` is applied. A field that was never set is omitted; a field
   explicitly set to ``None`` is transmitted as JSON ``null`` so the API can tell
   "leave this alone" apart from "clear this value".
"""

import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from permit.api.base import SimpleHttpClient
from permit.api.models import (
    ResourceInstanceUpdate,
    RoleAssignmentCreate,
    UserCreate,
    UserUpdate,
)
from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import BaseModel
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel
else:
    from pydantic.v1 import BaseModel

# Pins how the encoder renders a datetime without an offset.
FIXED_DATETIME = datetime.datetime(2024, 3, 1, 12, 30, 45)  # noqa: DTZ001 - naive on purpose
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
def captured(httpserver: HTTPServer) -> list[Any]:
    """Register a catch-all handler that records every received JSON body."""
    bodies: list[Any] = []

    def handler(request: Request) -> Response:
        bodies.append(request.get_json())
        return Response('{"ok": true}', status=200, content_type="application/json")

    httpserver.expect_request("/v2/echo").respond_with_handler(handler)
    return bodies


async def test_explicitly_set_none_is_transmitted_as_null(
    client: SimpleHttpClient, captured: list[Any]
) -> None:
    """An explicit ``email=None`` must reach the API as ``null``, not be dropped.

    Before the fix ``exclude_none=True`` removed it, so ``users.update()`` silently
    no-opped instead of clearing the email.
    """
    await client.patch("/echo", model=Ack, json=UserUpdate(email=None, first_name="Jane"))

    assert captured == [{"email": None, "first_name": "Jane"}]


async def test_never_set_field_is_omitted(client: SimpleHttpClient, captured: list[Any]) -> None:
    """``exclude_unset`` still applies: untouched fields never appear in the body."""
    await client.patch("/echo", model=Ack, json=UserUpdate(first_name="Jane"))

    assert captured == [{"first_name": "Jane"}]
    assert "email" not in captured[0]
    assert "last_name" not in captured[0]


async def test_null_inside_attributes_dict_is_preserved(
    client: SimpleHttpClient, captured: list[Any]
) -> None:
    """A ``null`` the caller put inside an ``attributes`` dict must survive.

    ``exclude_none`` recursed into plain dicts, so an attribute explicitly set to null
    was stripped instead of being stored as null.
    """
    await client.patch(
        "/echo",
        model=Ack,
        json=UserUpdate(attributes={"department": None, "age": 30, "nested": {"expired": None}}),
    )

    assert captured == [
        {"attributes": {"department": None, "age": 30, "nested": {"expired": None}}}
    ]


async def test_attributes_set_to_null_wholesale(
    client: SimpleHttpClient, captured: list[Any]
) -> None:
    """Clearing the whole attributes bag is expressible as ``attributes=None``.

    ``attributes`` defaults to ``{}``, so ``exclude_none`` made an explicit ``None``
    indistinguishable from never touching the field at all.
    """
    await client.patch("/echo", model=Ack, json=ResourceInstanceUpdate(attributes=None))

    assert captured == [{"attributes": None}]


async def test_raw_dict_with_datetime_uuid_and_enum_is_encoded(
    client: SimpleHttpClient, captured: list[Any]
) -> None:
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


async def test_raw_dict_keys_are_never_dropped(
    client: SimpleHttpClient, captured: list[Any]
) -> None:
    """Encoding a dict must not remove keys.

    The API schemas use ``Extra.forbid``, and a silently dropped key is how the
    original ``exclude_none`` bug manifested.
    """
    body = {"key": "user-1", "email": None, "first_name": None}

    await client.post("/echo", model=Ack, json=body)

    assert captured == [body]


async def test_list_body_encodes_each_item(client: SimpleHttpClient, captured: list[Any]) -> None:
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


async def test_no_body_stays_absent(client: SimpleHttpClient, httpserver: HTTPServer) -> None:
    """``json=None`` must not turn into a ``null`` body."""
    seen: list[bytes] = []

    def handler(request: Request) -> Response:
        seen.append(request.get_data())
        return Response('{"ok": true}', status=200, content_type="application/json")

    httpserver.expect_request("/v2/nobody").respond_with_handler(handler)

    await client.delete("/nobody", model=Ack, json=None)

    assert seen == [b""]


async def test_role_assignment_body_unchanged(
    client: SimpleHttpClient, captured: list[Any]
) -> None:
    """users.assign_role routes a model through this path; its body must not grow keys.

    The backend's ``UserRoleCreate.tenant``/``resource_instance`` are nullable, but an
    unset ``resource_instance`` still has to stay out of the body -- the backend rejects
    an assignment that carries neither, and the root validator only sees what we send.
    """
    assignment = RoleAssignmentCreate(role="admin", tenant="stripe-inc", user="jane")
    await client.post("/echo", model=Ack, json=assignment.copy(exclude={"user"}))

    assert captured == [{"role": "admin", "tenant": "stripe-inc"}]
