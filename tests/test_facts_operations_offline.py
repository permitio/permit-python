"""Offline wire tests for the bulk and single-object facts methods of ``permit.api`` (PER-16177).

They cover the bulk user, tenant and resource instance methods, the resource instance,
relationship tuple and role assignment methods that write or read one object, the bulk
relationship tuple and role assignment methods, ``tenants.list_tenant_users()`` and the user
invite methods. Each is called through the async and the blocking client, each closed once
the call returns, on both routings: with ``proxy_facts_via_pdp`` off, which sends the
request to the API, and on, which sends it to the PDP's ``/facts`` route (the user invite
methods send it to the API either way). The test checks the request it puts on the wire
(method, path, query string, headers and JSON body), what the response parses into, and
that the API's error response raises the matching ``PermitApiError``. The API and the PDP
are each served by a local ``pytest_httpserver`` of their own and the API context is
pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

from typing import Any, NamedTuple

import pytest
from pydantic.v1 import BaseModel
from pytest_httpserver import HTTPServer

from permit.api.models import (
    BulkRoleAssignmentReport,
    BulkRoleUnAssignmentReport,
    ElementsUserInviteRead,
    PaginatedResultElementsUserInviteRead,
    PaginatedResultUserRead,
    RelationshipTupleCreateBulkOperationResult,
    RelationshipTupleDelete,
    RelationshipTupleDeleteBulkOperationResult,
    ResourceInstanceCreateBulkOperationResult,
    ResourceInstanceDeleteBulkOperationResult,
    ResourceInstanceRead,
    RoleAssignmentRead,
    RoleAssignmentRemove,
    TenantDeleteBulkOperationResult,
    UserCreate,
    UserCreateBulkOperationResult,
    UserDeleteBulkOperationResult,
    UserRead,
    UserReplaceBulkOperationResult,
)
from permit.api.user_invites import UserInvitesApi
from permit.config import PermitConfig
from permit.exceptions import PermitApiError, PermitValidationError
from tests.facts_methods import (
    ASSIGNMENT,
    INSTANCE,
    INSTANCE_ID,
    RESOURCE_INSTANCE,
    ROLE_ASSIGNMENT,
    TENANT_ID,
    TUPLE,
    TUPLE_IDENT,
    USER,
    USER_ID,
    read,
)
from tests.utils import (
    DUPLICATE,
    FACTS,
    FORBIDDEN,
    JSON_HEADERS,
    NOT_FOUND,
    ApiError,
    Call,
    call,
    invoke,
    offline_config,
    sent,
    sent_headers,
)

FLAVOURS = ["async", "sync"]


class Routing(NamedTuple):
    """The facts options of a client, and the wait-for-sync headers its requests carry."""

    options: dict[str, Any]
    wait_timeout: str | None
    timeout_policy: str | None


ROUTINGS = {
    "api": Routing({}, None, None),
    "pdp": Routing(
        {
            "proxy_facts_via_pdp": True,
            "facts_sync_timeout": 2.5,
            "facts_sync_timeout_policy": "fail",
        },
        "2.5",
        "fail",
    ),
}

INVALID = ApiError(
    422,
    {"detail": [{"loc": ["body", "operations"], "msg": "field required", "type": "missing"}]},
    PermitValidationError,
)


class Case(NamedTuple):
    """One method call, the request it sends on each routing, and what it returns.

    ``call`` is the method's dotted path under ``permit.api``. ``api_path`` is the request's
    path on the API, and ``pdp_path`` its path on the PDP with ``proxy_facts_via_pdp`` on, or
    None for a method that sends it to the API either way. ``response`` is the JSON the
    server answers with, or None for an empty 204, and ``model`` is what the method returns,
    or None when it returns nothing. ``error`` is the API error the error test answers with.
    """

    call: Call
    method: str
    api_path: str
    pdp_path: str | None
    query: list[tuple[str, str]]
    body: Any
    response: Any
    model: type[BaseModel] | None
    error: ApiError


DEFAULT_PAGE = [("page", "1"), ("per_page", "100")]
SECOND_PAGE = [("page", "2"), ("per_page", "10")]

USERS_PAGE = {"data": [USER], "total_count": 1, "page_count": 1}
NEW_USERS = [UserCreate(key="alice", email="alice@example.com"), {"key": "bob"}]
NEW_USERS_SENT = [{"key": "alice", "email": "alice@example.com"}, {"key": "bob"}]
OTHER_ASSIGNMENT = {"user": "bob", "role": "viewer", "tenant": "default"}

INVITE_ID = "6a1b2c3d-0000-4000-8000-000000000040"
ROLE_ID = "6a1b2c3d-0000-4000-8000-000000000050"
NEW_INVITE = {
    "key": "bob",
    "status": "pending",
    "email": "bob@example.com",
    "first_name": "Bob",
    "last_name": "Smith",
    "role_id": ROLE_ID,
    "tenant_id": TENANT_ID,
    "resource_instance_id": INSTANCE_ID,
}
INVITE = read(**NEW_INVITE, id=INVITE_ID)
INVITES_PAGE = {"data": [INVITE], "total_count": 1, "page_count": 1}
APPROVAL = {"email": "bob@example.com", "key": "bob", "attributes": {"dept": "eng"}}
INVITES = f"{FACTS}/user_invites"

CASES = {
    # bulk users and tenants
    "users.bulk_create": Case(
        call=call("users.bulk_create", NEW_USERS),
        method="POST",
        api_path=f"{FACTS}/bulk/users",
        pdp_path="/facts/bulk/users",
        query=[],
        body={"operations": NEW_USERS_SENT},
        response={},
        model=UserCreateBulkOperationResult,
        error=INVALID,
    ),
    "users.bulk_replace": Case(
        call=call("users.bulk_replace", NEW_USERS),
        method="PUT",
        api_path=f"{FACTS}/bulk/users",
        pdp_path="/facts/bulk/users",
        query=[],
        body={"operations": NEW_USERS_SENT},
        response={},
        model=UserReplaceBulkOperationResult,
        error=INVALID,
    ),
    "users.bulk_delete": Case(
        call=call("users.bulk_delete", ["alice", USER_ID]),
        method="DELETE",
        api_path=f"{FACTS}/bulk/users",
        pdp_path="/facts/bulk/users",
        query=[],
        body={"idents": ["alice", USER_ID]},
        response={},
        model=UserDeleteBulkOperationResult,
        error=INVALID,
    ),
    "tenants.bulk_delete": Case(
        call=call("tenants.bulk_delete", ["acme", TENANT_ID]),
        method="DELETE",
        api_path=f"{FACTS}/bulk/tenants",
        pdp_path="/facts/bulk/tenants",
        query=[],
        body={"idents": ["acme", TENANT_ID]},
        response={},
        model=TenantDeleteBulkOperationResult,
        error=INVALID,
    ),
    # tenant users
    "tenants.list_tenant_users": Case(
        call=call("tenants.list_tenant_users", "acme"),
        method="GET",
        api_path=f"{FACTS}/tenants/acme/users",
        pdp_path="/facts/tenants/acme/users",
        query=DEFAULT_PAGE,
        body=None,
        response=USERS_PAGE,
        model=PaginatedResultUserRead,
        error=NOT_FOUND,
    ),
    "tenants.list_tenant_users-page": Case(
        call=call("tenants.list_tenant_users", "acme", page=2, per_page=10),
        method="GET",
        api_path=f"{FACTS}/tenants/acme/users",
        pdp_path="/facts/tenants/acme/users",
        query=SECOND_PAGE,
        body=None,
        response={"data": [], "total_count": 1, "page_count": 1},
        model=PaginatedResultUserRead,
        error=NOT_FOUND,
    ),
    # relationship tuples
    "relationship_tuples.delete": Case(
        call=call("relationship_tuples.delete", TUPLE_IDENT),
        method="DELETE",
        api_path=f"{FACTS}/relationship_tuples",
        pdp_path="/facts/relationship_tuples",
        query=[],
        body=TUPLE_IDENT,
        response=None,
        model=None,
        error=NOT_FOUND,
    ),
    "relationship_tuples.delete-model": Case(
        call=call("relationship_tuples.delete", RelationshipTupleDelete(**TUPLE_IDENT)),
        method="DELETE",
        api_path=f"{FACTS}/relationship_tuples",
        pdp_path="/facts/relationship_tuples",
        query=[],
        body=TUPLE_IDENT,
        response=None,
        model=None,
        error=NOT_FOUND,
    ),
    "relationship_tuples.bulk_create": Case(
        call=call("relationship_tuples.bulk_create", [TUPLE]),
        method="POST",
        api_path=f"{FACTS}/relationship_tuples/bulk",
        pdp_path="/facts/relationship_tuples/bulk",
        query=[],
        body={"operations": [TUPLE]},
        response={},
        model=RelationshipTupleCreateBulkOperationResult,
        error=INVALID,
    ),
    "relationship_tuples.bulk_delete": Case(
        call=call("relationship_tuples.bulk_delete", [TUPLE_IDENT]),
        method="DELETE",
        api_path=f"{FACTS}/relationship_tuples/bulk",
        pdp_path="/facts/relationship_tuples/bulk",
        query=[],
        body={"idents": [TUPLE_IDENT]},
        response={},
        model=RelationshipTupleDeleteBulkOperationResult,
        error=INVALID,
    ),
    # resource instances
    "resource_instances.create": Case(
        call=call("resource_instances.create", INSTANCE),
        method="POST",
        api_path=f"{FACTS}/resource_instances",
        pdp_path="/facts/resource_instances",
        query=[],
        body=INSTANCE,
        response=RESOURCE_INSTANCE,
        model=ResourceInstanceRead,
        error=DUPLICATE,
    ),
    "resource_instances.get": Case(
        call=call("resource_instances.get", "document:readme"),
        method="GET",
        api_path=f"{FACTS}/resource_instances/document:readme",
        pdp_path="/facts/resource_instances/document:readme",
        query=[],
        body=None,
        response=RESOURCE_INSTANCE,
        model=ResourceInstanceRead,
        error=NOT_FOUND,
    ),
    "resource_instances.get_by_key": Case(
        call=call("resource_instances.get_by_key", "document:readme"),
        method="GET",
        api_path=f"{FACTS}/resource_instances/document:readme",
        pdp_path="/facts/resource_instances/document:readme",
        query=[],
        body=None,
        response=RESOURCE_INSTANCE,
        model=ResourceInstanceRead,
        error=NOT_FOUND,
    ),
    "resource_instances.get_by_id": Case(
        call=call("resource_instances.get_by_id", INSTANCE_ID),
        method="GET",
        api_path=f"{FACTS}/resource_instances/{INSTANCE_ID}",
        pdp_path=f"/facts/resource_instances/{INSTANCE_ID}",
        query=[],
        body=None,
        response=RESOURCE_INSTANCE,
        model=ResourceInstanceRead,
        error=NOT_FOUND,
    ),
    "resource_instances.update": Case(
        call=call("resource_instances.update", "document:readme", {"attributes": {"pages": 3}}),
        method="PATCH",
        api_path=f"{FACTS}/resource_instances/document:readme",
        pdp_path="/facts/resource_instances/document:readme",
        query=[],
        body={"attributes": {"pages": 3}},
        response=RESOURCE_INSTANCE,
        model=ResourceInstanceRead,
        error=NOT_FOUND,
    ),
    "resource_instances.delete": Case(
        call=call("resource_instances.delete", "document:readme"),
        method="DELETE",
        api_path=f"{FACTS}/resource_instances/document:readme",
        pdp_path="/facts/resource_instances/document:readme",
        query=[],
        body=None,
        response=None,
        model=None,
        error=NOT_FOUND,
    ),
    "resource_instances.bulk_replace": Case(
        call=call("resource_instances.bulk_replace", [INSTANCE]),
        method="PUT",
        api_path=f"{FACTS}/bulk/resource_instances",
        pdp_path="/facts/bulk/resource_instances",
        query=[],
        body={"operations": [INSTANCE]},
        response={},
        model=ResourceInstanceCreateBulkOperationResult,
        error=INVALID,
    ),
    "resource_instances.bulk_delete": Case(
        call=call("resource_instances.bulk_delete", ["document:readme", INSTANCE_ID]),
        method="DELETE",
        api_path=f"{FACTS}/bulk/resource_instances",
        pdp_path="/facts/bulk/resource_instances",
        query=[],
        body={"idents": ["document:readme", INSTANCE_ID]},
        response={},
        model=ResourceInstanceDeleteBulkOperationResult,
        error=INVALID,
    ),
    # role assignments
    "role_assignments.assign": Case(
        call=call("role_assignments.assign", ASSIGNMENT),
        method="POST",
        api_path=f"{FACTS}/role_assignments",
        pdp_path="/facts/role_assignments",
        query=[],
        body=ASSIGNMENT,
        response=ROLE_ASSIGNMENT,
        model=RoleAssignmentRead,
        error=DUPLICATE,
    ),
    "role_assignments.unassign": Case(
        call=call("role_assignments.unassign", RoleAssignmentRemove(**ASSIGNMENT)),
        method="DELETE",
        api_path=f"{FACTS}/role_assignments",
        pdp_path="/facts/role_assignments",
        query=[],
        body=ASSIGNMENT,
        response=None,
        model=None,
        error=NOT_FOUND,
    ),
    "role_assignments.bulk_assign": Case(
        call=call("role_assignments.bulk_assign", [ASSIGNMENT, OTHER_ASSIGNMENT]),
        method="POST",
        api_path=f"{FACTS}/role_assignments/bulk",
        pdp_path="/facts/role_assignments/bulk",
        query=[],
        body=[ASSIGNMENT, OTHER_ASSIGNMENT],
        response={"assignments_created": 2},
        model=BulkRoleAssignmentReport,
        error=INVALID,
    ),
    "role_assignments.bulk_unassign": Case(
        call=call("role_assignments.bulk_unassign", [ASSIGNMENT, OTHER_ASSIGNMENT]),
        method="DELETE",
        api_path=f"{FACTS}/role_assignments/bulk",
        pdp_path="/facts/role_assignments/bulk",
        query=[],
        body=[ASSIGNMENT, OTHER_ASSIGNMENT],
        response={"assignments_removed": 2},
        model=BulkRoleUnAssignmentReport,
        error=INVALID,
    ),
    # user invites, which go to the API with or without proxy_facts_via_pdp
    "user_invites.list": Case(
        call=call("user_invites.list"),
        method="GET",
        api_path=INVITES,
        pdp_path=None,
        query=DEFAULT_PAGE,
        body=None,
        response=INVITES_PAGE,
        model=PaginatedResultElementsUserInviteRead,
        error=FORBIDDEN,
    ),
    "user_invites.list-page": Case(
        call=call("user_invites.list", page=2, per_page=10),
        method="GET",
        api_path=INVITES,
        pdp_path=None,
        query=SECOND_PAGE,
        body=None,
        response={"data": [], "total_count": 1, "page_count": 1},
        model=PaginatedResultElementsUserInviteRead,
        error=FORBIDDEN,
    ),
    "user_invites.get": Case(
        call=call("user_invites.get", INVITE_ID),
        method="GET",
        api_path=f"{INVITES}/{INVITE_ID}",
        pdp_path=None,
        query=[],
        body=None,
        response=INVITE,
        model=ElementsUserInviteRead,
        error=NOT_FOUND,
    ),
    "user_invites.create": Case(
        call=call("user_invites.create", NEW_INVITE),
        method="POST",
        api_path=INVITES,
        pdp_path=None,
        query=[],
        body=NEW_INVITE,
        response=INVITE,
        model=ElementsUserInviteRead,
        error=DUPLICATE,
    ),
    "user_invites.delete": Case(
        call=call("user_invites.delete", INVITE_ID),
        method="DELETE",
        api_path=f"{INVITES}/{INVITE_ID}",
        pdp_path=None,
        query=[],
        body=None,
        response=None,
        model=None,
        error=NOT_FOUND,
    ),
    "user_invites.approve": Case(
        call=call("user_invites.approve", INVITE_ID, APPROVAL),
        method="POST",
        api_path=f"{INVITES}/{INVITE_ID}/approve",
        pdp_path=None,
        query=[],
        body=APPROVAL,
        response={**USER, "key": "bob", "email": "bob@example.com", "attributes": {"dept": "eng"}},
        model=UserRead,
        error=NOT_FOUND,
    ),
}


@pytest.fixture
def pdp_server(httpserver_ipv4: HTTPServer) -> HTTPServer:
    """A server of its own for the PDP, so a request reaching it is told from one to the API."""
    return httpserver_ipv4


def make_config(api: HTTPServer, pdp: HTTPServer, routing: Routing) -> PermitConfig:
    """An offline config for the API on ``api`` and the PDP on ``pdp``, routed by ``routing``."""
    offline = offline_config(api.url_for("").rstrip("/"))
    return PermitConfig(
        token=offline.token,
        api_url=offline.api_url,
        pdp=pdp.url_for("").rstrip("/"),
        api_context=offline.api_context,
        **routing.options,
    )


def destination(
    case: Case, routing: str, api: HTTPServer, pdp: HTTPServer
) -> tuple[HTTPServer, str, HTTPServer]:
    """The server the request must reach, its path there, and the server it must not reach."""
    if routing == "pdp" and case.pdp_path is not None:
        return pdp, case.pdp_path, api
    return api, case.api_path, pdp


def expected_headers(routing: Routing) -> dict[str, str | None]:
    return {
        **JSON_HEADERS,
        "X-Wait-Timeout": routing.wait_timeout,
        "X-Timeout-Policy": routing.timeout_policy,
    }


def test_every_public_user_invites_method_has_a_case() -> None:
    public = {
        f"user_invites.{name}"
        for name, value in vars(UserInvitesApi).items()
        if not name.startswith("_") and callable(value)
    }

    assert {case.call.path for case in CASES.values() if case.pdp_path is None} == public
    assert len(public) == 5


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("routing", ROUTINGS)
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_request_and_response(
    *, httpserver: HTTPServer, pdp_server: HTTPServer, case: Case, routing: str, flavour: str
) -> None:
    config = make_config(httpserver, pdp_server, ROUTINGS[routing])
    server, path, other = destination(case, routing, httpserver, pdp_server)
    handler = server.expect_request(path, method=case.method)
    if case.response is None:
        handler.respond_with_data("", status=204)
    else:
        handler.respond_with_json(case.response)

    result = invoke(config, flavour, case.call)

    assert [sent(request) for request, _ in server.log] == [
        {"method": case.method, "path": path, "query": case.query, "body": case.body}
    ]
    assert [sent_headers(request) for request, _ in server.log] == [
        expected_headers(ROUTINGS[routing])
    ]
    assert other.log == []
    if case.model is None:
        assert result is None
    else:
        assert type(result) is case.model
        assert result == case.model.parse_obj(case.response)


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("routing", ROUTINGS)
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_an_api_error_raises_the_matching_permit_api_error(
    *, httpserver: HTTPServer, pdp_server: HTTPServer, case: Case, routing: str, flavour: str
) -> None:
    """Through the PDP too: its ``/facts`` routes pass the API's error response on."""
    config = make_config(httpserver, pdp_server, ROUTINGS[routing])
    server, path, other = destination(case, routing, httpserver, pdp_server)
    server.expect_request(path, method=case.method).respond_with_json(
        case.error.body, status=case.error.status
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(config, flavour, case.call)

    assert type(raised.value) is case.error.raises
    assert raised.value.status_code == case.error.status
    assert raised.value.details == case.error.body
    assert len(server.log) == 1
    assert other.log == []
