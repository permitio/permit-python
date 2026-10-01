"""Offline tests for the detailed lists and the detailed_key deprecation (PER-16337).

``list_detailed()`` on ``role_assignments``, ``resource_instances`` and
``relationship_tuples`` is called through the async and the blocking client. The tests
check the request it puts on the wire (method, path, query string, headers and body) and
what the response parses into. For the same filters it must send exactly the query its
module's ``list()`` sends, to the ``/detailed`` route next to it.

``resource_instances.list(detailed_key=...)`` keeps sending what it sent in 3.0, and warns
once, at the line that called it, on both clients; a call without ``detailed_key`` does not
warn. Every request is served by a local ``pytest_httpserver`` and the API context is
pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
import warnings
from operator import attrgetter
from typing import Any, NamedTuple

import pytest
from pydantic.v1 import BaseModel
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.api.models import (
    PaginatedResultRelationshipTupleDetailedRead,
    PaginatedResultResourceInstanceDetailedRead,
    PaginatedResultRoleAssignmentDetailedRead,
    RelationshipTupleBlockRead,
    RelationshipTupleDetailedRead,
    ResourceInstanceBlockRead,
    ResourceInstanceDetailedRead,
    RoleAssignmentDetailedRead,
    RoleAssignmentResourceInstance,
    RoleAssignmentUser,
    StrippedRelationBlockRead,
    TenantBlockRead,
)
from permit.config import PermitConfig
from permit.exceptions import PermitApiError, PermitContextError, PermitNotFoundError
from permit.sync import Permit as SyncPermit
from tests.utils import FACTS, ORG, PROJECT, Call, call, sent

FLAVOURS = ["async", "sync"]

# The headers the SDK sets. The wait-for-sync ones are listed so that sending one shows.
HEADERS = ("Authorization", "Content-Type", "X-Wait-Timeout", "X-Timeout-Policy")
JSON_HEADERS: dict[str, str | None] = {
    "Authorization": "Bearer test-token",
    "Content-Type": "application/json",
    "X-Wait-Timeout": None,
    "X-Timeout-Policy": None,
}

NOW = "2024-01-01T00:00:00+00:00"
SCOPE = {
    "organization_id": "00000000-0000-4000-8000-000000000001",
    "project_id": "00000000-0000-4000-8000-000000000002",
    "environment_id": "00000000-0000-4000-8000-000000000003",
}
TENANT_ID = "00000000-0000-4000-8000-000000000004"

ROLE_ASSIGNMENT_DETAILED = {
    "id": "00000000-0000-4000-8000-000000000010",
    "role": {
        "id": "00000000-0000-4000-8000-000000000011",
        "key": "editor",
        "name": "Editor",
        "permissions": ["document:read", "document:edit"],
    },
    "user": {
        "id": "00000000-0000-4000-8000-000000000012",
        "key": "alice",
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "attributes": {"dept": "eng"},
    },
    "tenant": {"id": TENANT_ID, "key": "t1", "name": "T1", "attributes": {"tier": "gold"}},
    "resource_instance": {
        "id": "00000000-0000-4000-8000-000000000013",
        "key": "readme",
        "resource": "document",
        "attributes": {"public": False},
    },
    **SCOPE,
    "created_at": NOW,
}
RESOURCE_INSTANCE_DETAILED = {
    "key": "readme",
    "tenant": "t1",
    "resource": "document",
    "id": "00000000-0000-4000-8000-000000000020",
    **SCOPE,
    "created_at": NOW,
    "updated_at": NOW,
    "resource_id": "00000000-0000-4000-8000-000000000021",
    "tenant_id": TENANT_ID,
    "attributes": {"public": False},
    "relationships": [
        {"subject": "folder:docs", "relation": "parent", "object": "document:readme"}
    ],
}
RELATIONSHIP_TUPLE_DETAILED = {
    "subject": "folder:docs",
    "relation": "parent",
    "object": "document:readme",
    "id": "00000000-0000-4000-8000-000000000030",
    "tenant": "t1",
    "subject_id": "00000000-0000-4000-8000-000000000031",
    "relation_id": "00000000-0000-4000-8000-000000000032",
    "object_id": "00000000-0000-4000-8000-000000000033",
    "tenant_id": TENANT_ID,
    **SCOPE,
    "created_at": NOW,
    "updated_at": NOW,
    "subject_details": {"key": "docs", "tenant": "t1", "resource": "folder", "attributes": {}},
    "relation_details": {"key": "parent", "name": "Parent", "description": "a folder's"},
    "object_details": {
        "key": "readme",
        "tenant": "t1",
        "resource": "document",
        "attributes": {"public": False},
    },
    "tenant_details": {"key": "t1", "name": "T1", "attributes": {"tier": "gold"}},
}


class Module(NamedTuple):
    """An API module with a list_detailed(), the page it is answered with, and its model."""

    page: dict[str, Any]
    model: type[BaseModel]


MODULES = {
    "role_assignments": Module(
        {"data": [ROLE_ASSIGNMENT_DETAILED], "total_count": 41, "page_count": 3},
        PaginatedResultRoleAssignmentDetailedRead,
    ),
    "resource_instances": Module(
        {"data": [RESOURCE_INSTANCE_DETAILED], "total_count": 1, "page_count": 1},
        PaginatedResultResourceInstanceDetailedRead,
    ),
    "relationship_tuples": Module(
        {"data": [RELATIONSHIP_TUPLE_DETAILED], "total_count": 1, "page_count": 1},
        PaginatedResultRelationshipTupleDetailedRead,
    ),
}
DEFAULT_PAGE = [("page", "1"), ("per_page", "100")]


class QueryCase(NamedTuple):
    """Filters passed to list() and list_detailed() of one module, and the query they send."""

    module: str
    kwargs: dict[str, Any]
    query: list[tuple[str, str]]


QUERY_CASES = {
    "role_assignments-defaults": QueryCase("role_assignments", {}, DEFAULT_PAGE),
    "role_assignments-lists": QueryCase(
        "role_assignments",
        {
            "user_key": ["alice", "bob"],
            "role_key": ["editor", "viewer"],
            "tenant_key": ["t1", "t2"],
            "resource_key": "document",
            "resource_instance_key": "document:readme",
            "page": 2,
            "per_page": 10,
        },
        sorted(
            [
                ("page", "2"),
                ("per_page", "10"),
                ("user", "alice"),
                ("user", "bob"),
                ("role", "editor"),
                ("role", "viewer"),
                ("tenant", "t1"),
                ("tenant", "t2"),
                ("resource", "document"),
                ("resource_instance", "document:readme"),
            ]
        ),
    ),
    "role_assignments-single-values": QueryCase(
        "role_assignments",
        {"user_key": "alice", "role_key": "editor", "tenant_key": "t1"},
        sorted([*DEFAULT_PAGE, ("user", "alice"), ("role", "editor"), ("tenant", "t1")]),
    ),
    "resource_instances-defaults": QueryCase("resource_instances", {}, DEFAULT_PAGE),
    "resource_instances-filters": QueryCase(
        "resource_instances",
        {
            "tenant_key": "t1",
            "resource_key": "document",
            "search_key": "readme",
            "page": 3,
            "per_page": 25,
        },
        sorted(
            [
                ("page", "3"),
                ("per_page", "25"),
                ("tenant", "t1"),
                ("resource", "document"),
                ("search", "readme"),
            ]
        ),
    ),
    "relationship_tuples-defaults": QueryCase("relationship_tuples", {}, DEFAULT_PAGE),
    "relationship_tuples-filters": QueryCase(
        "relationship_tuples",
        {
            "subject_key": "folder:docs",
            "relation_key": "parent",
            "object_key": "document:readme",
            "tenant_key": "t1",
            "page": 2,
            "per_page": 50,
        },
        sorted(
            [
                ("page", "2"),
                ("per_page", "50"),
                ("subject", "folder:docs"),
                ("relation", "parent"),
                ("object", "document:readme"),
                ("tenant", "t1"),
            ]
        ),
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


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


@pytest.fixture
def pdp_server(httpserver_ipv4: HTTPServer) -> HTTPServer:
    """A server of its own for the PDP, so a request reaching it is told from one to the API."""
    return httpserver_ipv4


@pytest.fixture
def split_config(config: PermitConfig, pdp_server: HTTPServer) -> PermitConfig:
    """The offline config with the API on ``httpserver`` and the PDP on ``pdp_server``."""
    config.pdp = pdp_server.url_for("").rstrip("/")
    return config


# --- list_detailed() -------------------------------------------------------------------


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", QUERY_CASES.values(), ids=QUERY_CASES.keys())
def test_list_detailed_sends_the_query_of_list_to_the_detailed_route(
    httpserver: HTTPServer, config: PermitConfig, case: QueryCase, flavour: str
) -> None:
    collection = f"{FACTS}/{case.module}"
    httpserver.expect_request(collection, method="GET").respond_with_json([])
    httpserver.expect_request(f"{collection}/detailed", method="GET").respond_with_json(
        MODULES[case.module].page
    )

    invoke(config, flavour, call(f"api.{case.module}.list", **case.kwargs))
    invoke(config, flavour, call(f"api.{case.module}.list_detailed", **case.kwargs))

    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": "GET", "path": collection, "query": case.query, "body": None},
        {"method": "GET", "path": f"{collection}/detailed", "query": case.query, "body": None},
    ]
    (listed, _), (detailed, _) = httpserver.log
    assert detailed.query_string == listed.query_string
    assert [sent_headers(request) for request, _ in httpserver.log] == [JSON_HEADERS] * 2


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("module", MODULES.keys())
def test_list_detailed_returns_the_page_as_its_detailed_model(
    httpserver: HTTPServer, config: PermitConfig, module: str, flavour: str
) -> None:
    page, model = MODULES[module]
    httpserver.expect_request(f"{FACTS}/{module}/detailed", method="GET").respond_with_json(page)

    result = invoke(config, flavour, call(f"api.{module}.list_detailed"))

    assert type(result) is model
    assert result == model.parse_obj(page)
    assert len(httpserver.log) == 1


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_role_assignments_list_detailed_parses_the_objects_each_assignment_names(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    page = MODULES["role_assignments"].page
    httpserver.expect_request(f"{FACTS}/role_assignments/detailed", method="GET").respond_with_json(
        page
    )

    result = invoke(config, flavour, call("api.role_assignments.list_detailed"))

    assert isinstance(result, PaginatedResultRoleAssignmentDetailedRead)
    assert (result.total_count, result.page_count) == (41, 3)
    (assignment,) = result.data
    assert type(assignment) is RoleAssignmentDetailedRead
    assert type(assignment.user) is RoleAssignmentUser
    assert (assignment.user.key, assignment.user.email) == ("alice", "alice@example.com")
    assert assignment.user.attributes == {"dept": "eng"}
    assert (assignment.role.key, assignment.role.permissions) == (
        "editor",
        ["document:read", "document:edit"],
    )
    assert (assignment.tenant.key, assignment.tenant.attributes) == ("t1", {"tier": "gold"})
    assert type(assignment.resource_instance) is RoleAssignmentResourceInstance
    assert (assignment.resource_instance.resource, assignment.resource_instance.key) == (
        "document",
        "readme",
    )


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_resource_instances_list_detailed_parses_the_relationships(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    page = MODULES["resource_instances"].page
    httpserver.expect_request(
        f"{FACTS}/resource_instances/detailed", method="GET"
    ).respond_with_json(page)

    result = invoke(config, flavour, call("api.resource_instances.list_detailed"))

    assert isinstance(result, PaginatedResultResourceInstanceDetailedRead)
    (instance,) = result.data
    assert type(instance) is ResourceInstanceDetailedRead
    assert instance.relationships == [
        RelationshipTupleBlockRead(
            subject="folder:docs", relation="parent", object="document:readme"
        )
    ]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_relationship_tuples_list_detailed_parses_the_details(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    page = MODULES["relationship_tuples"].page
    httpserver.expect_request(
        f"{FACTS}/relationship_tuples/detailed", method="GET"
    ).respond_with_json(page)

    result = invoke(config, flavour, call("api.relationship_tuples.list_detailed"))

    assert isinstance(result, PaginatedResultRelationshipTupleDetailedRead)
    (detailed,) = result.data
    assert type(detailed) is RelationshipTupleDetailedRead
    assert detailed.subject_details == ResourceInstanceBlockRead(
        key="docs", tenant="t1", resource="folder", attributes={}
    )
    assert detailed.relation_details == StrippedRelationBlockRead(
        key="parent", name="Parent", description="a folder's"
    )
    assert detailed.object_details is not None
    assert detailed.object_details.key == "readme"
    assert detailed.tenant_details == TenantBlockRead(
        key="t1", name="T1", attributes={"tier": "gold"}
    )


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("proxy_facts_via_pdp", [False, True], ids=["api", "proxy-via-pdp"])
@pytest.mark.parametrize("module", MODULES.keys())
def test_list_detailed_follows_proxy_facts_via_pdp_as_list_does(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    split_config: PermitConfig,
    module: str,
    proxy_facts_via_pdp: bool,
    flavour: str,
) -> None:
    """With proxy_facts_via_pdp, the PDP forwards the read to the API, as it does for list()."""
    split_config.proxy_facts_via_pdp = proxy_facts_via_pdp
    path = f"/facts/{module}/detailed" if proxy_facts_via_pdp else f"{FACTS}/{module}/detailed"
    server, other = (pdp_server, httpserver) if proxy_facts_via_pdp else (httpserver, pdp_server)
    server.expect_request(path, method="GET").respond_with_json(MODULES[module].page)

    invoke(split_config, flavour, call(f"api.{module}.list_detailed", page=2))

    assert [sent(request) for request, _ in server.log] == [
        {"method": "GET", "path": path, "query": [("page", "2"), ("per_page", "100")], "body": None}
    ]
    assert other.log == []


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("module", MODULES.keys())
def test_list_detailed_raises_the_api_error(
    httpserver: HTTPServer, config: PermitConfig, module: str, flavour: str
) -> None:
    detail = {
        "id": "request-1",
        "title": "Not found",
        "error_code": "NOT_FOUND",
        "message": "The tenant does not exist",
    }
    httpserver.expect_request(f"{FACTS}/{module}/detailed", method="GET").respond_with_json(
        detail, status=404
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(config, flavour, call(f"api.{module}.list_detailed", tenant_key="missing"))

    assert type(raised.value) is PermitNotFoundError
    assert raised.value.status_code == 404
    assert raised.value.details == detail
    assert len(httpserver.log) == 1


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("module", MODULES.keys())
def test_list_detailed_refuses_a_project_context_before_sending(
    httpserver: HTTPServer, config: PermitConfig, module: str, flavour: str
) -> None:
    """A project-level key needs the SDK's API context set to an environment first."""
    config.api_context._save_api_key_accessible_scope(org=ORG, project=PROJECT)
    config.api_context.set_project_level_context(ORG, PROJECT)

    with pytest.raises(PermitContextError):
        invoke(config, flavour, call(f"api.{module}.list_detailed"))

    assert httpserver.log == []


# --- resource_instances.list(detailed_key=...) -------------------------------------------

INSTANCES = f"{FACTS}/resource_instances"
DETAILED_KEY_WARNING = (
    "The detailed_key argument of permit.api.resource_instances.list() is deprecated and will "
    "be removed in permit 4.0; use permit.api.resource_instances.list_detailed() instead."
)


def list_blocking(permit: SyncPermit, target: Call) -> object:
    return permit.api.resource_instances.list(*target.args, **target.kwargs)


async def list_awaiting(permit: Permit, target: Call) -> object:
    return await permit.api.resource_instances.list(*target.args, **target.kwargs)


# The line each client's warning must name: the one statement of the helper above that
# calls list() on that client.
CALL_SITES = {
    "sync": (__file__, list_blocking.__code__.co_firstlineno + 1),
    "async": (__file__, list_awaiting.__code__.co_firstlineno + 1),
}


def call_list(config: PermitConfig, flavour: str, target: Call) -> list[tuple[str, str, int]]:
    """Call resource_instances.list(), and return the DeprecationWarnings it issued.

    Each warning is its message and the file and line it names. Other categories are left
    out: a ResourceWarning, for one, comes from garbage collection and can land anywhere.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if flavour == "async":
            asyncio.run(list_awaiting(Permit(config), target))
        else:
            list_blocking(SyncPermit(config), target)
    return [
        (str(warning.message), warning.filename, warning.lineno)
        for warning in caught
        if issubclass(warning.category, DeprecationWarning)
    ]


DETAILED_KEY_CALLS = {
    "true": (call("list", detailed_key=True), "true"),
    "false": (call("list", detailed_key=False), "false"),
    # A positional detailed_key is the case under test, so the bare boolean is the point.
    "positional": (call("list", 1, 100, None, None, True), "true"),  # noqa: FBT003
    "with-filters": (call("list", tenant_key="t1", detailed_key=True, search_key="r"), "true"),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("target", "detailed"), DETAILED_KEY_CALLS.values(), ids=DETAILED_KEY_CALLS.keys()
)
def test_detailed_key_warns_once_at_the_call_and_still_sends_the_detailed_flag(
    httpserver: HTTPServer, config: PermitConfig, target: Call, detailed: str, flavour: str
) -> None:
    httpserver.expect_request(INSTANCES, method="GET").respond_with_json([])

    caught = call_list(config, flavour, target)

    assert caught == [(DETAILED_KEY_WARNING, *CALL_SITES[flavour])]
    ((request, _),) = httpserver.log
    assert ("detailed", detailed) in sent(request)["query"]
    assert request.args.getlist("detailed") == [detailed]


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    "target",
    [call("list"), call("list", detailed_key=None), call("list", 2, 10, "t1", "document")],
    ids=["no-arguments", "detailed-key-none", "other-filters"],
)
def test_list_without_detailed_key_neither_warns_nor_sends_the_flag(
    httpserver: HTTPServer, config: PermitConfig, target: Call, flavour: str
) -> None:
    httpserver.expect_request(INSTANCES, method="GET").respond_with_json([])

    assert call_list(config, flavour, target) == []
    ((request, _),) = httpserver.log
    assert "detailed" not in request.args
