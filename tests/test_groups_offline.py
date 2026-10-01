"""Offline tests for permit.api.groups (PER-16677).

Every public method is called through the async and the blocking client, and the test
checks the request it puts on the wire (method, path, query string, headers and JSON
body) and the model the response parses into. Every request is served by a local
``pytest_httpserver`` and the API context is pre-populated, so no API key and no
``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
from operator import attrgetter
from typing import Any, NamedTuple

import pytest
from pydantic.v1 import BaseModel, ValidationError
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.api.groups import GroupsApi
from permit.api.models import (
    GroupAddRole,
    GroupAssignment,
    GroupCreate,
    GroupRead,
    GroupReadSchema,
    PaginatedResultGroupReadSchema,
)
from permit.config import PermitConfig
from permit.exceptions import PermitApiError
from permit.sync import Permit as SyncPermit
from tests.utils import SCHEMA, Call, call, sent

GROUPS = f"{SCHEMA}/groups"
GROUP_ID = "00000000-0000-4000-8000-000000000010"
USER_ID = "00000000-0000-4000-8000-000000000011"
DEFAULT_PAGE = [("page", "1"), ("per_page", "100")]
SECOND_PAGE = [("page", "2"), ("per_page", "10")]

GROUP_SCHEMA = {
    "id": GROUP_ID,
    "group_resource_type_key": "group",
    "group_instance_key": "engineering",
    "group_tenant": "default",
}
GROUP_READ = {
    "group_resource_type_key": "group",
    "group_instance_key": "engineering",
    "group_tenant": "default",
    "assigned_roles": ["document:readme#editor", "group:engineering#member"],
    "users": [USER_ID],
}
GROUP_PAGE = {"data": [GROUP_SCHEMA], "total_count": 1, "page_count": 1}

NEW_GROUP = {"group_instance_key": "engineering", "group_tenant": "default"}
TEAM_GROUP = {
    "group_resource_type_key": "team",
    "group_instance_key": "engineering",
    "group_tenant": "default",
}
ROLE = {
    "role": "editor",
    "resource": "document",
    "resource_instance": "readme",
    "tenant": "default",
}
MEMBER_GROUP = {"group_instance_key": "leads"}


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
    response: dict[str, Any] | None
    model: type[BaseModel] | None


CASES = {
    "list": Case(
        call=call("list"),
        method="GET",
        path=f"{GROUPS}/direct",
        query=DEFAULT_PAGE,
        body=None,
        response=GROUP_PAGE,
        model=PaginatedResultGroupReadSchema,
    ),
    "list-page": Case(
        call=call("list", page=2, per_page=10),
        method="GET",
        path=f"{GROUPS}/direct",
        query=SECOND_PAGE,
        body=None,
        response=GROUP_PAGE,
        model=PaginatedResultGroupReadSchema,
    ),
    "get": Case(
        call=call("get", "engineering"),
        method="GET",
        path=f"{GROUPS}/direct/engineering",
        query=[],
        body=None,
        response=GROUP_SCHEMA,
        model=GroupReadSchema,
    ),
    "get-by-type-and-key": Case(
        call=call("get", "team:engineering"),
        method="GET",
        path=f"{GROUPS}/direct/team:engineering",
        query=[],
        body=None,
        response=GROUP_SCHEMA,
        model=GroupReadSchema,
    ),
    "get-by-id": Case(
        call=call("get", GROUP_ID),
        method="GET",
        path=f"{GROUPS}/direct/{GROUP_ID}",
        query=[],
        body=None,
        response=GROUP_SCHEMA,
        model=GroupReadSchema,
    ),
    "create": Case(
        call=call("create", GroupCreate(**NEW_GROUP)),
        method="POST",
        path=GROUPS,
        query=[],
        body=NEW_GROUP,
        response=GROUP_READ,
        model=GroupRead,
    ),
    "create-dict": Case(
        call=call("create", NEW_GROUP),
        method="POST",
        path=GROUPS,
        query=[],
        body=NEW_GROUP,
        response=GROUP_READ,
        model=GroupRead,
    ),
    "create-other-resource-type": Case(
        call=call("create", TEAM_GROUP),
        method="POST",
        path=GROUPS,
        query=[],
        body=TEAM_GROUP,
        response={**GROUP_READ, "group_resource_type_key": "team"},
        model=GroupRead,
    ),
    "delete": Case(
        call=call("delete", "group:engineering"),
        method="DELETE",
        path=f"{GROUPS}/group:engineering",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    "assign_user": Case(
        call=call("assign_user", "engineering", "alice", "default"),
        method="PUT",
        path=f"{GROUPS}/engineering/users/alice",
        query=[],
        body={"tenant": "default"},
        response=GROUP_READ,
        model=GroupRead,
    ),
    "assign_user-keywords": Case(
        call=call("assign_user", group_instance_key=GROUP_ID, user_key=USER_ID, tenant="t-2"),
        method="PUT",
        path=f"{GROUPS}/{GROUP_ID}/users/{USER_ID}",
        query=[],
        body={"tenant": "t-2"},
        response=GROUP_READ,
        model=GroupRead,
    ),
    "remove_user": Case(
        call=call("remove_user", "group:engineering", "alice", "default"),
        method="DELETE",
        path=f"{GROUPS}/group:engineering/users/alice",
        query=[],
        body={"tenant": "default"},
        response=None,
        model=None,
    ),
    "assign_role": Case(
        call=call("assign_role", "engineering", GroupAddRole(**ROLE)),
        method="POST",
        path=f"{GROUPS}/engineering/roles",
        query=[],
        body=ROLE,
        response=GROUP_READ,
        model=GroupRead,
    ),
    "assign_role-dict": Case(
        call=call("assign_role", "engineering", ROLE),
        method="POST",
        path=f"{GROUPS}/engineering/roles",
        query=[],
        body=ROLE,
        response=GROUP_READ,
        model=GroupRead,
    ),
    "remove_role": Case(
        call=call("remove_role", "engineering", GroupAddRole(**ROLE)),
        method="DELETE",
        path=f"{GROUPS}/engineering/roles",
        query=[],
        body=ROLE,
        response=None,
        model=None,
    ),
    "remove_role-dict": Case(
        call=call("remove_role", "engineering", ROLE),
        method="DELETE",
        path=f"{GROUPS}/engineering/roles",
        query=[],
        body=ROLE,
        response=None,
        model=None,
    ),
    "assign_group": Case(
        call=call("assign_group", "engineering", GroupAssignment(**MEMBER_GROUP)),
        method="PUT",
        path=f"{GROUPS}/engineering/assign_group",
        query=[],
        body=MEMBER_GROUP,
        response=GROUP_READ,
        model=GroupRead,
    ),
    "assign_group-dict": Case(
        call=call("assign_group", "engineering", MEMBER_GROUP),
        method="PUT",
        path=f"{GROUPS}/engineering/assign_group",
        query=[],
        body=MEMBER_GROUP,
        response=GROUP_READ,
        model=GroupRead,
    ),
    "remove_group": Case(
        call=call("remove_group", "engineering", GroupAssignment(**MEMBER_GROUP)),
        method="DELETE",
        path=f"{GROUPS}/engineering/assign_group",
        query=[],
        body=MEMBER_GROUP,
        response=None,
        model=None,
    ),
    "remove_group-dict": Case(
        call=call("remove_group", "engineering", MEMBER_GROUP),
        method="DELETE",
        path=f"{GROUPS}/engineering/assign_group",
        query=[],
        body=MEMBER_GROUP,
        response=None,
        model=None,
    ),
}

# The case named after each method, for the error tests.
BASIC_CASES = {name: case for name, case in CASES.items() if name == case.call.path}

# A model argument given as a dict that misses a required field, for each method that
# takes one.
INVALID_DICTS = {
    "create": call("create", {"group_tenant": "default"}),
    "assign_role": call("assign_role", "engineering", {"role": "editor", "tenant": "default"}),
    "remove_role": call("remove_role", "engineering", {"role": "editor", "tenant": "default"}),
    "assign_group": call("assign_group", "engineering", {}),
    "remove_group": call("remove_group", "engineering", {}),
}


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``permit.api.groups.<target.path>`` on the async or the blocking client."""
    permit = Permit(config) if flavour == "async" else SyncPermit(config)
    method = attrgetter(f"api.groups.{target.path}")(permit)
    result = method(*target.args, **target.kwargs)
    if flavour == "async":
        return asyncio.run(result)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in ("Authorization", "Content-Type")}


def test_every_public_method_has_a_case() -> None:
    public = {
        name
        for name, value in vars(GroupsApi).items()
        if not name.startswith("_") and callable(value)
    }

    assert {case.call.path for case in CASES.values()} == public
    assert set(BASIC_CASES) == public
    assert len(public) == 10


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
    else:
        assert type(result) is case.model
        assert result == case.model.parse_obj(case.response)


@pytest.mark.parametrize("flavour", ["async", "sync"])
@pytest.mark.parametrize("status", [404, 409])
@pytest.mark.parametrize("case", BASIC_CASES.values(), ids=BASIC_CASES.keys())
def test_error_status_raises_permit_api_error(
    httpserver: HTTPServer, config: PermitConfig, case: Case, status: int, flavour: str
) -> None:
    detail = {"error_code": "ERROR", "message": f"status {status}"}
    httpserver.expect_request(case.path, method=case.method).respond_with_json(
        detail, status=status
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(config, flavour, case.call)

    assert raised.value.status_code == status
    assert raised.value.details == detail
    assert len(httpserver.log) == 1


@pytest.mark.parametrize("flavour", ["async", "sync"])
@pytest.mark.parametrize("target", INVALID_DICTS.values(), ids=INVALID_DICTS.keys())
def test_an_invalid_dict_is_rejected_before_sending(
    httpserver: HTTPServer, config: PermitConfig, target: Call, flavour: str
) -> None:
    with pytest.raises(ValidationError):
        invoke(config, flavour, target)

    assert httpserver.log == []
