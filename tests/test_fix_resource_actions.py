"""Offline tests for permit.api.resource_actions and permit.api.action_groups (PER-16177).

Every public method is called through the async and the blocking client, and the
test checks the request it puts on the wire (method, path, query string and JSON
body) and the model the response parses into. Every request is served by a local
``pytest_httpserver`` and the API context is pre-populated, so no API key and no
``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
import json
from operator import attrgetter
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.api.context import ApiContext
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
from permit.sync import Permit as SyncPermit

ORG = "test-org"
PROJECT = "test-project"
ENVIRONMENT = "test-env"
RESOURCES = f"/v2/schema/{PROJECT}/{ENVIRONMENT}/resources"
TIMESTAMP = "2024-01-01T00:00:00+00:00"
RESOURCE_ID = "00000000-0000-4000-8000-000000000005"
ACTION_ID = "00000000-0000-4000-8000-000000000006"
GROUP_ID = "00000000-0000-4000-8000-000000000007"
DEFAULT_PAGE = [("page", "1"), ("per_page", "100")]
SECOND_PAGE = [("page", "2"), ("per_page", "10")]


def common(key: str, object_id: str) -> Dict[str, Any]:
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


def action(key: str) -> Dict[str, Any]:
    return {**common(key, ACTION_ID), "permission_name": f"document:{key}"}


def group(key: str) -> Dict[str, Any]:
    return {**common(key, GROUP_ID), "actions": ["read", "write"]}


class Call(NamedTuple):
    """A method, by the dotted path a user writes, and the arguments to call it with."""

    path: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


def call(path: str, *args: Any, **kwargs: Any) -> Call:
    return Call(path, args, kwargs)


class Case(NamedTuple):
    """One SDK call and the request it must send.

    ``response`` is the JSON the server answers with, or None for an empty 204;
    ``model`` is what it parses into, or None when the method returns nothing.
    """

    call: Call
    method: str
    path: str
    query: List[Tuple[str, str]]
    body: Any
    response: Union[Dict[str, Any], List[Dict[str, Any]], None]
    model: Optional[type]


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
        call=call(f"{ACTIONS}.create", "document", {"key": "write", "name": "Write", "attributes": {"risk": "high"}}),
        method="POST",
        path=f"{RESOURCES}/document/actions",
        query=[],
        body={"key": "write", "name": "Write", "attributes": {"risk": "high"}},
        response=action("write"),
        model=ResourceActionRead,
    ),
    "actions.update": Case(
        call=call(f"{ACTIONS}.update", "document", "write", ResourceActionUpdate(name="Write access")),
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
        call=call(f"{GROUPS}.update", "document", "editors", ResourceActionGroupUpdate(actions=["read"])),
        method="PATCH",
        path=f"{RESOURCES}/document/action_groups/editors",
        query=[],
        body={"actions": ["read"]},
        response=group("editors"),
        model=ResourceActionGroupRead,
    ),
    "action_groups.update-clears-a-field": Case(
        call=call(f"{GROUPS}.update", "document", "editors", {"name": "Editors", "description": None}),
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


def offline_config(base_url: str) -> PermitConfig:
    """Build a PermitConfig whose context is already resolved to environment level."""
    api_context = ApiContext()
    api_context._save_api_key_accessible_scope(org=ORG, project=PROJECT, environment=ENVIRONMENT)
    api_context.set_environment_level_context(ORG, PROJECT, ENVIRONMENT)
    return PermitConfig(token="test-token", api_url=base_url, pdp=base_url, api_context=api_context)


def sent(request: Request) -> Dict[str, Any]:
    """What a request put on the wire."""
    body = request.get_data()
    return {
        "method": request.method,
        "path": request.path,
        "query": sorted(request.args.items(multi=True)),
        "body": json.loads(body) if body else None,
    }


def public_methods(api: type) -> set:
    return {name for name, value in vars(api).items() if not name.startswith("_") and callable(value)}


def test_every_public_method_has_a_case():
    expected = {f"{ACTIONS}.{name}" for name in public_methods(ResourceActionsApi)} | {
        f"{GROUPS}.{name}" for name in public_methods(ResourceActionGroupsApi)
    }

    assert {case.call.path for case in CASES.values()} == expected
    assert len(expected) == 14


@pytest.mark.parametrize("flavour", ["async", "sync"])
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_request_and_response(httpserver: HTTPServer, case: Case, flavour: str):
    handler = httpserver.expect_request(case.path, method=case.method)
    if case.response is None:
        handler.respond_with_data("", status=204)
    else:
        handler.respond_with_json(case.response)

    config = offline_config(httpserver.url_for("").rstrip("/"))
    permit = Permit(config) if flavour == "async" else SyncPermit(config)
    method = attrgetter(case.call.path.removeprefix("permit."))(permit)
    result = method(*case.call.args, **case.call.kwargs)
    if flavour == "async":
        result = asyncio.run(result)
    else:
        assert not inspect.isawaitable(result)

    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": case.method, "path": case.path, "query": case.query, "body": case.body}
    ]
    if case.model is None:
        assert result is None
    elif isinstance(case.response, list):
        assert [type(item) for item in result] == [case.model] * len(case.response)
        assert result == [case.model.parse_obj(item) for item in case.response]
    else:
        assert type(result) is case.model
        assert result == case.model.parse_obj(case.response)
