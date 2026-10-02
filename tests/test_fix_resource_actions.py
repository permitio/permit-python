"""Offline tests for permit.api.resource_actions and permit.api.action_groups (PER-16177).

Every public method is called through the async and the blocking client, each closed
once the call returns, and the test checks the request it puts on the wire (method,
path, query string, headers and JSON body), the model the response parses into, and
that the API's error response raises the matching ``PermitApiError``. Every request is
served by a local ``pytest_httpserver`` and the API context is pre-populated, so no API
key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
from operator import attrgetter
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.api.models import (
    ResourceActionCreate,
    ResourceActionGroupCreate,
    ResourceActionGroupRead,
    ResourceActionGroupUpdate,
    ResourceActionRead,
    ResourceActionUpdate,
)
from permit.api.resource_action_groups import ResourceActionGroupsApi
from permit.api.resource_actions import ResourceActionsApi
from permit.config import PermitConfig
from permit.exceptions import PermitApiError, PermitNotFoundError
from permit.sync import Permit as SyncPermit
from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import BaseModel
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel
else:
    from pydantic.v1 import BaseModel
from tests.utils import SCHEMA, Call, call, sent

RESOURCES = f"{SCHEMA}/resources"
TIMESTAMP = "2024-01-01T00:00:00+00:00"
RESOURCE_ID = "00000000-0000-4000-8000-000000000005"
ACTION_ID = "00000000-0000-4000-8000-000000000006"
GROUP_ID = "00000000-0000-4000-8000-000000000007"
DEFAULT_PAGE = [("page", "1"), ("per_page", "100")]
SECOND_PAGE = [("page", "2"), ("per_page", "10")]


def common(key: str, object_id: str) -> dict[str, Any]:
    return {
        "key": key,
        "name": key.title(),
        "id": object_id,
        "organization_id": "00000000-0000-4000-8000-000000000002",
        "project_id": "00000000-0000-4000-8000-000000000003",
        "environment_id": "00000000-0000-4000-8000-000000000004",
        "resource_id": RESOURCE_ID,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }


def action(key: str) -> dict[str, Any]:
    return {**common(key, ACTION_ID), "permission_name": f"document:{key}"}


def group(key: str) -> dict[str, Any]:
    return {**common(key, GROUP_ID), "actions": ["read", "write"]}


class Case(NamedTuple):
    """One SDK call and the request it must send.

    ``response`` is the JSON the server answers with, or None for an empty 204;
    ``model`` is what it parses into, or None when the method returns nothing.
    """

    call: Call
    method: str
    path: str
    query: list[tuple[str, str]]
    body: Any
    response: dict[str, Any] | list[dict[str, Any]] | None
    model: type[BaseModel] | None


ACTIONS = "permit.api.resource_actions"
GROUPS = "permit.api.action_groups"

CASES = {
    "actions.list": Case(
        call=call(f"{ACTIONS}.list", "document"),
        method="GET",
        path=f"{RESOURCES}/document/actions",
        query=DEFAULT_PAGE,
        body=None,
        response=[action("read"), action("write")],
        model=ResourceActionRead,
    ),
    "actions.list-paginated": Case(
        call=call(f"{ACTIONS}.list", "document", page=2, per_page=10),
        method="GET",
        path=f"{RESOURCES}/document/actions",
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ResourceActionRead,
    ),
    "actions.get": Case(
        call=call(f"{ACTIONS}.get", "document", "read"),
        method="GET",
        path=f"{RESOURCES}/document/actions/read",
        query=[],
        body=None,
        response=action("read"),
        model=ResourceActionRead,
    ),
    "actions.get_by_key": Case(
        call=call(f"{ACTIONS}.get_by_key", "document", "read"),
        method="GET",
        path=f"{RESOURCES}/document/actions/read",
        query=[],
        body=None,
        response=action("read"),
        model=ResourceActionRead,
    ),
    "actions.get_by_id": Case(
        call=call(f"{ACTIONS}.get_by_id", RESOURCE_ID, ACTION_ID),
        method="GET",
        path=f"{RESOURCES}/{RESOURCE_ID}/actions/{ACTION_ID}",
        query=[],
        body=None,
        response=action("read"),
        model=ResourceActionRead,
    ),
    "actions.create": Case(
        call=call(f"{ACTIONS}.create", "document", ResourceActionCreate(key="write", name="Write")),
        method="POST",
        path=f"{RESOURCES}/document/actions",
        query=[],
        body={"key": "write", "name": "Write"},
        response=action("write"),
        model=ResourceActionRead,
    ),
    "actions.create-from-dict": Case(
        call=call(
            f"{ACTIONS}.create",
            "document",
            {"key": "write", "name": "Write", "attributes": {"risk": "high"}},
        ),
        method="POST",
        path=f"{RESOURCES}/document/actions",
        query=[],
        body={"key": "write", "name": "Write", "attributes": {"risk": "high"}},
        response=action("write"),
        model=ResourceActionRead,
    ),
    "actions.update": Case(
        call=call(
            f"{ACTIONS}.update", "document", "write", ResourceActionUpdate(name="Write access")
        ),
        method="PATCH",
        path=f"{RESOURCES}/document/actions/write",
        query=[],
        body={"name": "Write access"},
        response=action("write"),
        model=ResourceActionRead,
    ),
    "actions.update-clears-a-field": Case(
        call=call(f"{ACTIONS}.update", "document", "write", {"description": None}),
        method="PATCH",
        path=f"{RESOURCES}/document/actions/write",
        query=[],
        body={"description": None},
        response=action("write"),
        model=ResourceActionRead,
    ),
    "actions.delete": Case(
        call=call(f"{ACTIONS}.delete", "document", "write"),
        method="DELETE",
        path=f"{RESOURCES}/document/actions/write",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    "action_groups.list": Case(
        call=call(f"{GROUPS}.list", "document"),
        method="GET",
        path=f"{RESOURCES}/document/action_groups",
        query=DEFAULT_PAGE,
        body=None,
        response=[group("editors")],
        model=ResourceActionGroupRead,
    ),
    "action_groups.list-paginated": Case(
        call=call(f"{GROUPS}.list", "document", page=2, per_page=10),
        method="GET",
        path=f"{RESOURCES}/document/action_groups",
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ResourceActionGroupRead,
    ),
    "action_groups.get": Case(
        call=call(f"{GROUPS}.get", "document", "editors"),
        method="GET",
        path=f"{RESOURCES}/document/action_groups/editors",
        query=[],
        body=None,
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.get_by_key": Case(
        call=call(f"{GROUPS}.get_by_key", "document", "editors"),
        method="GET",
        path=f"{RESOURCES}/document/action_groups/editors",
        query=[],
        body=None,
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.get_by_id": Case(
        call=call(f"{GROUPS}.get_by_id", RESOURCE_ID, GROUP_ID),
        method="GET",
        path=f"{RESOURCES}/{RESOURCE_ID}/action_groups/{GROUP_ID}",
        query=[],
        body=None,
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.create": Case(
        call=call(
            f"{GROUPS}.create",
            "document",
            ResourceActionGroupCreate(key="editors", name="Editors", actions=["read", "write"]),
        ),
        method="POST",
        path=f"{RESOURCES}/document/action_groups",
        query=[],
        body={"key": "editors", "name": "Editors", "actions": ["read", "write"]},
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.create-from-dict": Case(
        call=call(f"{GROUPS}.create", "document", {"key": "editors", "name": "Editors"}),
        method="POST",
        path=f"{RESOURCES}/document/action_groups",
        query=[],
        body={"key": "editors", "name": "Editors"},
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.update": Case(
        call=call(
            f"{GROUPS}.update", "document", "editors", ResourceActionGroupUpdate(actions=["read"])
        ),
        method="PATCH",
        path=f"{RESOURCES}/document/action_groups/editors",
        query=[],
        body={"actions": ["read"]},
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.update-clears-a-field": Case(
        call=call(
            f"{GROUPS}.update", "document", "editors", {"name": "Editors", "description": None}
        ),
        method="PATCH",
        path=f"{RESOURCES}/document/action_groups/editors",
        query=[],
        body={"name": "Editors", "description": None},
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.delete": Case(
        call=call(f"{GROUPS}.delete", "document", "editors"),
        method="DELETE",
        path=f"{RESOURCES}/document/action_groups/editors",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
}


def public_methods(api: type) -> set[str]:
    return {
        name for name, value in vars(api).items() if not name.startswith("_") and callable(value)
    }


def test_every_public_method_has_a_case() -> None:
    expected = {f"{ACTIONS}.{name}" for name in public_methods(ResourceActionsApi)} | {
        f"{GROUPS}.{name}" for name in public_methods(ResourceActionGroupsApi)
    }

    assert {case.call.path for case in CASES.values()} == expected
    assert len(expected) == 14


async def _invoke_async(config: PermitConfig, target: Call) -> object:
    async with Permit(config) as permit:
        method = attrgetter(target.path.removeprefix("permit."))(permit)
        return await method(*target.args, **target.kwargs)


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``target`` on a new async or blocking client, then close the client."""
    if flavour == "async":
        return asyncio.run(_invoke_async(config, target))
    with SyncPermit(config) as permit:
        method = attrgetter(target.path.removeprefix("permit."))(permit)
        result = method(*target.args, **target.kwargs)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in ("Authorization", "Content-Type")}


@pytest.mark.parametrize("flavour", ["async", "sync"])
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_request_and_response(
    httpserver: HTTPServer, config: PermitConfig, case: Case, flavour: str
) -> None:
    handler = httpserver.expect_request(case.path, method=case.method)
    if case.response is None:
        handler.respond_with_data("", status=204)
    else:
        handler.respond_with_json(case.response)

    result = invoke(config, flavour, case.call)

    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": case.method, "path": case.path, "query": case.query, "body": case.body}
    ]
    assert [sent_headers(request) for request, _ in httpserver.log] == [
        {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
    ]
    if case.model is None:
        assert result is None
    elif isinstance(case.response, list):
        assert isinstance(result, list)
        assert [type(item) for item in result] == [case.model] * len(case.response)
        assert result == [case.model.parse_obj(item) for item in case.response]
    else:
        assert type(result) is case.model
        assert result == case.model.parse_obj(case.response)


# The API's answer for a resource, action or action group that does not exist.
NOT_FOUND = {
    "id": "6a1b2c3d0000400080000000000000ee",
    "title": "Not found",
    "error_code": "NOT_FOUND",
    "message": "The resource document was not found.",
}


@pytest.mark.parametrize("flavour", ["async", "sync"])
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_an_api_error_raises_the_matching_permit_api_error(
    httpserver: HTTPServer, config: PermitConfig, case: Case, flavour: str
) -> None:
    httpserver.expect_request(case.path, method=case.method).respond_with_json(
        NOT_FOUND, status=404
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(config, flavour, case.call)

    assert type(raised.value) is PermitNotFoundError
    assert raised.value.status_code == 404
    assert raised.value.details == NOT_FOUND
    assert len(httpserver.log) == 1
