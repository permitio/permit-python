"""Offline tests pinning the PDP facts-proxy endpoints the SDK targets.

``TenantsApi.__bulk_operations`` used to build its PDP client against
``/facts/users``, so ``tenants.bulk_create()`` POSTed a tenant bulk operation to
the PDP's *users* route. These tests use ``pytest_httpserver`` as a stand-in PDP
and assert on the URL, method and body the SDK actually emits, for the bulk
operations and for every single-object write the SDK proxies through the PDP.
"""

import copy
import json
import re
import uuid
from operator import attrgetter
from typing import Any, Dict, List, Optional, Tuple

import pytest
from pytest_httpserver import HTTPServer

from permit import Permit, PermitConfig
from permit.api.models import ResourceInstanceCreate, TenantCreate, UserCreate
from tests.utils import Call, call

ORG_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())
ENV_ID = str(uuid.uuid4())
NOW = "2024-01-01T00:00:00+00:00"

SCOPE_PATH = "/v2/api-key/scope"

RecordedRequest = Tuple[str, str, dict]


def _make_permit(
    httpserver: HTTPServer, *, proxy_facts_via_pdp: bool, response: Optional[Dict[str, Any]] = None
) -> Permit:
    """Build a Permit client whose PDP *and* REST API both point at ``httpserver``.

    The api-key scope lookup is served first so the SDK's context checks resolve to an
    environment-level key without touching the network; a catch-all handler answers every
    other route with ``response`` (default ``{}``) so we can observe which one the SDK picked.
    """
    base_url = httpserver.url_for("").rstrip("/")
    httpserver.expect_request(SCOPE_PATH, method="GET").respond_with_json(
        {
            "organization_id": ORG_ID,
            "project_id": PROJECT_ID,
            "environment_id": ENV_ID,
        }
    )
    httpserver.expect_request(re.compile(r".*")).respond_with_json(response or {})
    return Permit(
        PermitConfig(
            token="fake-api-key",
            pdp=base_url,
            api_url=base_url,
            proxy_facts_via_pdp=proxy_facts_via_pdp,
        )
    )


def _facts_requests(httpserver: HTTPServer) -> List[RecordedRequest]:
    """Every request the SDK made, except the api-key scope bootstrap call."""
    requests = []
    for request, _response in httpserver.log:
        if request.path == SCOPE_PATH:
            continue
        body = request.get_data(as_text=True)
        requests.append((request.method, request.path, json.loads(body) if body else {}))
    return requests


async def test_tenants_bulk_create_targets_the_pdp_tenants_endpoint(httpserver: HTTPServer):
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.tenants.bulk_create([TenantCreate(key="tenant-1", name="Tenant 1")])

    assert _facts_requests(httpserver) == [
        (
            "POST",
            "/facts/bulk/tenants",
            {"operations": [{"key": "tenant-1", "name": "Tenant 1"}]},
        )
    ]
    httpserver.check_assertions()


async def test_tenants_bulk_delete_targets_the_pdp_tenants_endpoint(httpserver: HTTPServer):
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.tenants.bulk_delete(["tenant-1", "tenant-2"])

    assert _facts_requests(httpserver) == [("DELETE", "/facts/bulk/tenants", {"idents": ["tenant-1", "tenant-2"]})]
    httpserver.check_assertions()


async def test_tenant_bulk_operations_never_reach_the_users_endpoint(httpserver: HTTPServer):
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.tenants.bulk_create([TenantCreate(key="tenant-1", name="Tenant 1")])
    await permit.api.tenants.bulk_delete(["tenant-1"])

    paths = {path for _method, path, _body in _facts_requests(httpserver)}
    assert paths == {"/facts/bulk/tenants"}


async def test_users_bulk_create_targets_the_pdp_users_endpoint(httpserver: HTTPServer):
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.users.bulk_create([UserCreate(key="user-1")])

    assert _facts_requests(httpserver) == [("POST", "/facts/bulk/users", {"operations": [{"key": "user-1"}]})]


async def test_resource_instances_bulk_operations_target_their_pdp_endpoint(httpserver: HTTPServer):
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.resource_instances.bulk_replace(
        [ResourceInstanceCreate(key="acc-1", resource="Account", tenant="tenant-1")]
    )
    await permit.api.resource_instances.bulk_delete(["Account:acc-1"])

    assert _facts_requests(httpserver) == [
        (
            "PUT",
            "/facts/bulk/resource_instances",
            {"operations": [{"key": "acc-1", "resource": "Account", "tenant": "tenant-1"}]},
        ),
        ("DELETE", "/facts/bulk/resource_instances", {"idents": ["Account:acc-1"]}),
    ]


async def test_tenants_bulk_create_without_pdp_proxy_targets_the_rest_api(httpserver: HTTPServer):
    permit = _make_permit(httpserver, proxy_facts_via_pdp=False)

    await permit.api.tenants.bulk_create([TenantCreate(key="tenant-1", name="Tenant 1")])

    assert _facts_requests(httpserver) == [
        (
            "POST",
            f"/v2/facts/{PROJECT_ID}/{ENV_ID}/bulk/tenants",
            {"operations": [{"key": "tenant-1", "name": "Tenant 1"}]},
        )
    ]


def _read_payload(**fields: Any) -> Dict[str, Any]:
    """A facts read-model response: the ids and timestamps they all require, plus ``fields``."""
    return {
        "id": str(uuid.uuid4()),
        "organization_id": ORG_ID,
        "project_id": PROJECT_ID,
        "environment_id": ENV_ID,
        "created_at": NOW,
        "updated_at": NOW,
        **fields,
    }


ROLE_ASSIGNMENT = {"user": "user-1", "role": "admin", "tenant": "tenant-1"}
ROLE_ASSIGNMENT_READ = _read_payload(
    **ROLE_ASSIGNMENT, user_id=str(uuid.uuid4()), role_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4())
)
RELATIONSHIP_TUPLE = {"subject": "folder:f-1", "relation": "parent", "object": "document:doc-1", "tenant": "tenant-1"}
RESOURCE_INSTANCE = {"key": "doc-1", "resource": "document", "tenant": "tenant-1"}

# Each single-object write the SDK proxies through the PDP, called on ``permit.api``; the one
# request it must send; and a response its read model parses, so only the route can differ.
SINGLE_WRITES = [
    pytest.param(
        call("users.create", {"key": "user-1"}),
        ("POST", "/facts/users", {"key": "user-1"}),
        _read_payload(key="user-1"),
        id="users.create",
    ),
    pytest.param(
        call("tenants.create", {"key": "tenant-1", "name": "Tenant 1"}),
        ("POST", "/facts/tenants", {"key": "tenant-1", "name": "Tenant 1"}),
        _read_payload(key="tenant-1", name="Tenant 1", last_action_at=NOW),
        id="tenants.create",
    ),
    pytest.param(
        call("resource_instances.create", RESOURCE_INSTANCE),
        ("POST", "/facts/resource_instances", RESOURCE_INSTANCE),
        _read_payload(**RESOURCE_INSTANCE, resource_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4())),
        id="resource_instances.create",
    ),
    pytest.param(
        call("relationship_tuples.create", RELATIONSHIP_TUPLE),
        ("POST", "/facts/relationship_tuples", RELATIONSHIP_TUPLE),
        _read_payload(
            **RELATIONSHIP_TUPLE,
            subject_id=str(uuid.uuid4()),
            relation_id=str(uuid.uuid4()),
            object_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
        ),
        id="relationship_tuples.create",
    ),
    pytest.param(
        call("role_assignments.assign", ROLE_ASSIGNMENT),
        ("POST", "/facts/role_assignments", ROLE_ASSIGNMENT),
        ROLE_ASSIGNMENT_READ,
        id="role_assignments.assign",
    ),
    pytest.param(
        call("users.assign_role", ROLE_ASSIGNMENT),
        ("POST", "/facts/users/user-1/roles", {"role": "admin", "tenant": "tenant-1"}),
        ROLE_ASSIGNMENT_READ,
        id="users.assign_role",
    ),
]


@pytest.mark.parametrize(("target", "expected", "response"), SINGLE_WRITES)
async def test_single_fact_writes_target_their_pdp_endpoint(
    httpserver: HTTPServer, target: Call, expected: RecordedRequest, response: Dict[str, Any]
):
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True, response=response)
    # A copy, so an SDK that edited the caller's dict could not also edit the expected body.
    args, kwargs = copy.deepcopy((target.args, target.kwargs))

    await attrgetter(target.path)(permit.api)(*args, **kwargs)

    assert _facts_requests(httpserver) == [expected]
