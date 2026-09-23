"""Offline tests pinning the PDP facts-proxy endpoints the SDK targets.

``TenantsApi.__bulk_operations`` used to build its PDP client against
``/facts/users``, so ``tenants.bulk_create()`` POSTed a tenant bulk operation to
the PDP's *users* route. These tests use ``pytest_httpserver`` as a stand-in PDP
and assert on the URL, method and body the SDK actually emits.
"""

import json
import re
import uuid
from typing import Any

from pytest_httpserver import HTTPServer

from permit import Permit, PermitConfig
from permit.api.models import ResourceInstanceCreate, TenantCreate, UserCreate

ORG_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())
ENV_ID = str(uuid.uuid4())

SCOPE_PATH = "/v2/api-key/scope"

RecordedRequest = tuple[str, str, dict[str, Any]]


def _make_permit(httpserver: HTTPServer, *, proxy_facts_via_pdp: bool) -> Permit:
    """Build a Permit client whose PDP *and* REST API both point at ``httpserver``.

    The api-key scope lookup is served first so the SDK's context checks resolve to an
    environment-level key without touching the network; a catch-all handler answers every
    other route with ``{}`` so we can observe which one the SDK picked.
    """
    base_url = httpserver.url_for("").rstrip("/")
    httpserver.expect_request(SCOPE_PATH, method="GET").respond_with_json(
        {
            "organization_id": ORG_ID,
            "project_id": PROJECT_ID,
            "environment_id": ENV_ID,
        }
    )
    httpserver.expect_request(re.compile(r".*")).respond_with_json({})
    return Permit(
        PermitConfig(
            token="fake-api-key",
            pdp=base_url,
            api_url=base_url,
            proxy_facts_via_pdp=proxy_facts_via_pdp,
        )
    )


def _facts_requests(httpserver: HTTPServer) -> list[RecordedRequest]:
    """Every request the SDK made, except the api-key scope bootstrap call."""
    requests = []
    for request, _response in httpserver.log:
        if request.path == SCOPE_PATH:
            continue
        body = request.get_data(as_text=True)
        requests.append((request.method, request.path, json.loads(body) if body else {}))
    return requests


async def test_tenants_bulk_create_targets_the_pdp_tenants_endpoint(httpserver: HTTPServer) -> None:
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


async def test_tenants_bulk_delete_targets_the_pdp_tenants_endpoint(httpserver: HTTPServer) -> None:
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.tenants.bulk_delete(["tenant-1", "tenant-2"])

    assert _facts_requests(httpserver) == [
        ("DELETE", "/facts/bulk/tenants", {"idents": ["tenant-1", "tenant-2"]})
    ]
    httpserver.check_assertions()


async def test_tenant_bulk_operations_never_reach_the_users_endpoint(
    httpserver: HTTPServer,
) -> None:
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.tenants.bulk_create([TenantCreate(key="tenant-1", name="Tenant 1")])
    await permit.api.tenants.bulk_delete(["tenant-1"])

    paths = {path for _method, path, _body in _facts_requests(httpserver)}
    assert paths == {"/facts/bulk/tenants"}


async def test_users_bulk_create_targets_the_pdp_users_endpoint(httpserver: HTTPServer) -> None:
    permit = _make_permit(httpserver, proxy_facts_via_pdp=True)

    await permit.api.users.bulk_create([UserCreate(key="user-1")])

    assert _facts_requests(httpserver) == [
        ("POST", "/facts/bulk/users", {"operations": [{"key": "user-1"}]})
    ]


async def test_resource_instances_bulk_operations_target_their_pdp_endpoint(
    httpserver: HTTPServer,
) -> None:
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


async def test_tenants_bulk_create_without_pdp_proxy_targets_the_rest_api(
    httpserver: HTTPServer,
) -> None:
    permit = _make_permit(httpserver, proxy_facts_via_pdp=False)

    await permit.api.tenants.bulk_create([TenantCreate(key="tenant-1", name="Tenant 1")])

    assert _facts_requests(httpserver) == [
        (
            "POST",
            f"/v2/facts/{PROJECT_ID}/{ENV_ID}/bulk/tenants",
            {"operations": [{"key": "tenant-1", "name": "Tenant 1"}]},
        )
    ]
