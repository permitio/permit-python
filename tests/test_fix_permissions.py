"""Offline tests pinning the permission strings the SDK puts on the wire.

A role's ``permissions`` list has two different formats, and the server decides
which one applies from the kind of role:

* a top level (tenant) role takes ``"{resource_key}:{action_key}"`` -- the server
  splits the string on the first colon;
* a *resource* role takes a bare ``"{action_key}"`` -- the role already belongs to
  a resource, so the server reads the whole string as an action key of that
  resource, and returns it in the same form.

Sending ``"document:read"`` for a resource role therefore asks for an action keyed
``"document:read"`` and fails with ``MISSING_PERMISSIONS ... 'document:document:read'``
-- the doubled prefix is the server quoting the resource it searched plus the key it
was given, not the SDK concatenating anything.

These tests hold the SDK to exactly that: it forwards each permission string
byte-for-byte, for both role kinds, so neither a helpful ``resource:`` prefix nor a
helpful strip can be added without CI noticing. The same applies to the
``resource_instance`` role-assignment filter, which is a resource instance string
(``resource:key`` or an instance uuid), never a bare instance key.
"""

import json
import uuid
from typing import Any, Dict, List

from pytest_httpserver import HTTPServer

from permit import Permit, PermitConfig
from permit.api.models import ResourceRoleCreate, RoleCreate

ORG_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())
ENV_ID = str(uuid.uuid4())

SCOPE_PATH = "/v2/api-key/scope"
RESOURCE_KEY = "document"
ROLE_KEY = "editor"

RESOURCE_ROLES_PATH = f"/v2/schema/{PROJECT_ID}/{ENV_ID}/resources/{RESOURCE_KEY}/roles"
RESOURCE_ROLE_PERMISSIONS_PATH = f"{RESOURCE_ROLES_PATH}/{ROLE_KEY}/permissions"
ROLES_PATH = f"/v2/schema/{PROJECT_ID}/{ENV_ID}/roles"
ROLE_ASSIGNMENTS_PATH = f"/v2/facts/{PROJECT_ID}/{ENV_ID}/role_assignments"


def _make_permit(httpserver: HTTPServer) -> Permit:
    """A Permit client whose REST API points at ``httpserver``."""
    base_url = httpserver.url_for("").rstrip("/")
    httpserver.expect_request(SCOPE_PATH, method="GET").respond_with_json(
        {
            "organization_id": ORG_ID,
            "project_id": PROJECT_ID,
            "environment_id": ENV_ID,
        }
    )
    return Permit(
        PermitConfig(
            token="fake-api-key",
            pdp=base_url,
            api_url=base_url,
        )
    )


def _resource_role_response(permissions: List[str]) -> Dict[str, Any]:
    """One ``ResourceRoleRead`` as the backend serializes it (bare action keys)."""
    return {
        "id": str(uuid.uuid4()),
        "key": ROLE_KEY,
        "name": "Editor",
        "description": "can edit a document",
        "permissions": permissions,
        "extends": [],
        "attributes": {},
        "organization_id": ORG_ID,
        "project_id": PROJECT_ID,
        "environment_id": ENV_ID,
        "resource_id": str(uuid.uuid4()),
        "resource": RESOURCE_KEY,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
    }


def _role_response(permissions: List[str]) -> Dict[str, Any]:
    """One ``RoleRead`` as the backend serializes it (``resource:action`` strings)."""
    return {
        "id": str(uuid.uuid4()),
        "key": "admin",
        "name": "Admin",
        "description": "can do everything",
        "permissions": permissions,
        "extends": [],
        "attributes": {},
        "organization_id": ORG_ID,
        "project_id": PROJECT_ID,
        "environment_id": ENV_ID,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
    }


def _sent_body(httpserver: HTTPServer, path: str, method: str) -> Dict[str, Any]:
    """The JSON body of the single request the SDK made to ``path``."""
    requests = [request for request, _response in httpserver.log if request.path == path and request.method == method]
    assert len(requests) == 1, f"expected exactly one {method} {path}, got {len(requests)}"
    return json.loads(requests[0].get_data(as_text=True))


async def test_resource_role_create_sends_bare_action_keys(httpserver: HTTPServer):
    """``resource_roles.create`` must forward the action keys it was given, unprefixed."""
    httpserver.expect_request(RESOURCE_ROLES_PATH, method="POST").respond_with_json(
        _resource_role_response(["read", "update"])
    )
    permit = _make_permit(httpserver)

    created = await permit.api.resource_roles.create(
        RESOURCE_KEY,
        ResourceRoleCreate(key=ROLE_KEY, name="Editor", permissions=["read", "update"]),
    )

    assert _sent_body(httpserver, RESOURCE_ROLES_PATH, "POST")["permissions"] == ["read", "update"]
    assert created.permissions == ["read", "update"]
    httpserver.check_assertions()


async def test_resource_role_create_does_not_strip_a_caller_supplied_prefix(httpserver: HTTPServer):
    """A caller who sends ``resource:action`` gets it on the wire, verbatim.

    The SDK must not paper over the format mismatch: the server's
    ``MISSING_PERMISSIONS ... 'document:document:read'`` is the signal that tells a
    caller they used the top level role format for a resource role.
    """
    httpserver.expect_request(RESOURCE_ROLES_PATH, method="POST").respond_with_json(
        _resource_role_response([f"{RESOURCE_KEY}:read"])
    )
    permit = _make_permit(httpserver)

    await permit.api.resource_roles.create(
        RESOURCE_KEY,
        ResourceRoleCreate(key=ROLE_KEY, name="Editor", permissions=[f"{RESOURCE_KEY}:read"]),
    )

    assert _sent_body(httpserver, RESOURCE_ROLES_PATH, "POST")["permissions"] == [f"{RESOURCE_KEY}:read"]
    httpserver.check_assertions()


async def test_resource_role_assign_permissions_sends_bare_action_keys(httpserver: HTTPServer):
    """``assign_permissions`` must send exactly the strings it was handed."""
    httpserver.expect_request(RESOURCE_ROLE_PERMISSIONS_PATH, method="POST").respond_with_json(
        _resource_role_response(["read", "update"])
    )
    permit = _make_permit(httpserver)

    granted = await permit.api.resource_roles.assign_permissions(RESOURCE_KEY, ROLE_KEY, ["update"])

    assert _sent_body(httpserver, RESOURCE_ROLE_PERMISSIONS_PATH, "POST") == {"permissions": ["update"]}
    assert granted.permissions == ["read", "update"]
    httpserver.check_assertions()


async def test_resource_role_remove_permissions_sends_bare_action_keys(httpserver: HTTPServer):
    """``remove_permissions`` carries its body on a DELETE, unprefixed."""
    httpserver.expect_request(RESOURCE_ROLE_PERMISSIONS_PATH, method="DELETE").respond_with_json(
        _resource_role_response(["read"])
    )
    permit = _make_permit(httpserver)

    revoked = await permit.api.resource_roles.remove_permissions(RESOURCE_KEY, ROLE_KEY, ["update"])

    assert _sent_body(httpserver, RESOURCE_ROLE_PERMISSIONS_PATH, "DELETE") == {"permissions": ["update"]}
    assert revoked.permissions == ["read"]
    httpserver.check_assertions()


async def test_top_level_role_create_keeps_the_resource_qualified_form(httpserver: HTTPServer):
    """A tenant role's permissions are ``resource:action`` and must not be rewritten."""
    permissions = [f"{RESOURCE_KEY}:read", f"{RESOURCE_KEY}:update", "folder:read"]
    httpserver.expect_request(ROLES_PATH, method="POST").respond_with_json(_role_response(permissions))
    permit = _make_permit(httpserver)

    created = await permit.api.roles.create(RoleCreate(key="admin", name="Admin", permissions=permissions))

    assert _sent_body(httpserver, ROLES_PATH, "POST")["permissions"] == permissions
    assert created.permissions == permissions
    httpserver.check_assertions()


async def test_role_assignment_filters_send_the_instance_ident_verbatim(httpserver: HTTPServer):
    """``resource_instance_key`` is a ``resource:key`` ident and travels unchanged.

    The server reads this filter as a resource instance string and answers 400 to
    anything that is neither ``resource:key`` nor an instance uuid.
    """
    httpserver.expect_request(ROLE_ASSIGNMENTS_PATH, method="GET").respond_with_json([])
    permit = _make_permit(httpserver)

    await permit.api.role_assignments.list(
        user_key="user-1",
        resource_key=RESOURCE_KEY,
        resource_instance_key=f"{RESOURCE_KEY}:readme",
        per_page=50,
    )

    requests = [request for request, _response in httpserver.log if request.path == ROLE_ASSIGNMENTS_PATH]
    assert len(requests) == 1
    assert requests[0].args["resource_instance"] == f"{RESOURCE_KEY}:readme"
    assert requests[0].args["resource"] == RESOURCE_KEY
    assert requests[0].args["user"] == "user-1"
    httpserver.check_assertions()
