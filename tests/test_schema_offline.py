"""Offline tests for the schema APIs of permit.api (PER-16177).

The APIs are ``resources``, ``resource_attributes``, ``resource_relations``,
``resource_roles``, ``roles``, ``condition_sets`` and ``condition_set_rules``. Every public
method is called through the async and the blocking client, each closed once the call
returns, and the test checks the request it puts on the wire (method, path, query string,
headers and JSON body), the type the response parses into, and the error that an API error
response raises.

None of these methods follows ``proxy_facts_via_pdp``: with it on, their requests still go
to the API, ``condition_set_rules`` included, whose routes are under ``/v2/facts``. Every
request is served by a local ``pytest_httpserver`` and the API context is pre-populated, so
no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

from typing import Any, NamedTuple

import pytest
from pydantic.v1 import BaseModel
from pytest_httpserver import HTTPServer

from permit.api.condition_set_rules import ConditionSetRulesApi
from permit.api.condition_sets import ConditionSetsApi
from permit.api.models import (
    AttributeType,
    ConditionSetCreate,
    ConditionSetRead,
    ConditionSetRuleCreate,
    ConditionSetRuleRead,
    ConditionSetRuleRemove,
    ConditionSetType,
    ConditionSetUpdate,
    DerivedRoleRuleCreate,
    DerivedRoleRuleDelete,
    DerivedRoleRuleRead,
    PaginatedResultRelationRead,
    PermitBackendSchemasSchemaDerivedRoleRuleDerivationSettings,
    RelationCreate,
    RelationRead,
    ResourceAttributeCreate,
    ResourceAttributeRead,
    ResourceAttributeUpdate,
    ResourceCreate,
    ResourceRead,
    ResourceReplace,
    ResourceRoleCreate,
    ResourceRoleRead,
    ResourceRoleUpdate,
    ResourceUpdate,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)
from permit.api.resource_attributes import ResourceAttributesApi
from permit.api.resource_relations import ResourceRelationsApi
from permit.api.resource_roles import ResourceRolesApi
from permit.api.resources import ResourcesApi
from permit.api.roles import RolesApi
from permit.config import PermitConfig
from permit.exceptions import PermitApiDetailedError, PermitApiError, PermitValidationError
from tests.utils import (
    DUPLICATE,
    FACTS,
    JSON_HEADERS,
    NOT_FOUND,
    SCHEMA,
    ApiError,
    Call,
    call,
    error_details,
    invoke,
    offline_config,
    sent,
    sent_headers,
)

FLAVOURS = ["async", "sync"]

# The schema APIs, by the attribute of permit.api that holds each.
SCHEMA_APIS: dict[str, type] = {
    "resources": ResourcesApi,
    "resource_attributes": ResourceAttributesApi,
    "resource_relations": ResourceRelationsApi,
    "resource_roles": ResourceRolesApi,
    "roles": RolesApi,
    "condition_sets": ConditionSetsApi,
    "condition_set_rules": ConditionSetRulesApi,
}

RESOURCES = f"{SCHEMA}/resources"
DOCUMENT = f"{RESOURCES}/document"
ROLES = f"{SCHEMA}/roles"
CONDITION_SETS = f"{SCHEMA}/condition_sets"
SET_RULES = f"{FACTS}/set_rules"

TIMESTAMP = "2026-01-01T00:00:00+00:00"
RESOURCE_ID = "6a1b2c3d-0000-4000-8000-000000000101"
FOLDER_ID = "6a1b2c3d-0000-4000-8000-000000000102"
ACTION_ID = "6a1b2c3d-0000-4000-8000-000000000103"
ATTRIBUTE_ID = "6a1b2c3d-0000-4000-8000-000000000104"
RELATION_ID = "6a1b2c3d-0000-4000-8000-000000000105"
ROLE_ID = "6a1b2c3d-0000-4000-8000-000000000106"
CONDITION_SET_ID = "6a1b2c3d-0000-4000-8000-000000000107"
RULE_ID = "6a1b2c3d-0000-4000-8000-000000000108"

DEFAULT_PAGE = [("page", "1"), ("per_page", "100")]
SECOND_PAGE = [("page", "2"), ("per_page", "10")]


def read(object_id: str, **fields: Any) -> dict[str, Any]:
    """A read model's JSON: its ``object_id``, ``fields``, and what every read model has."""
    return {
        "id": object_id,
        "organization_id": "6a1b2c3d-0000-4000-8000-000000000001",
        "project_id": "6a1b2c3d-0000-4000-8000-000000000002",
        "environment_id": "6a1b2c3d-0000-4000-8000-000000000003",
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        **fields,
    }


# --- what the API answers with ---------------------------------------------------------

RESOURCE = read(
    RESOURCE_ID,
    key="document",
    name="Document",
    actions={"read": {"id": ACTION_ID, "key": "read", "name": "Read"}},
)
ATTRIBUTE = read(
    ATTRIBUTE_ID,
    key="owner",
    type="string",
    resource_id=RESOURCE_ID,
    resource_key="document",
    built_in=False,
)
RELATION = read(
    RELATION_ID,
    key="parent",
    name="Parent",
    subject_resource="folder",
    subject_resource_id=FOLDER_ID,
    object_resource="document",
    object_resource_id=RESOURCE_ID,
)
RELATION_PAGE = {"data": [RELATION], "total_count": 1, "page_count": 1}
RESOURCE_ROLE = read(
    ROLE_ID,
    key="editor",
    name="Editor",
    resource="document",
    resource_id=RESOURCE_ID,
    permissions=["document:read", "document:write"],
)
DERIVATION = {
    "role_id": ROLE_ID,
    "resource_id": FOLDER_ID,
    "relation_id": RELATION_ID,
    "role": "editor",
    "on_resource": "folder",
    "linked_by_relation": "parent",
    "when": {"no_direct_roles_on_object": False},
}
DERIVATION_SETTINGS = {"no_direct_roles_on_object": True}
ROLE = read(ROLE_ID, key="admin", name="Admin", permissions=["document:read"])
CONDITIONS = {"allOf": [{"user.location": {"equals": "US"}}]}
CONDITION_SET = read(
    CONDITION_SET_ID, key="us_employees", name="US employees", type="userset", conditions=CONDITIONS
)
RULE = read(
    RULE_ID,
    key="us_employees_document:read_private_docs",
    user_set="us_employees",
    permission="document:read",
    resource_set="private_docs",
)

# --- what the SDK sends ----------------------------------------------------------------

NEW_RESOURCE = {
    "key": "document",
    "name": "Document",
    "actions": {"read": {}, "write": {"name": "Write"}},
    "attributes": {"owner": {"type": "string"}},
}
REPLACEMENT = {
    "name": "Document",
    "actions": {"read": {}},
    "roles": {"viewer": {"name": "Viewer", "permissions": ["read"]}},
    "relations": {"parent": "folder"},
}
NEW_ATTRIBUTE = {"key": "owner", "type": "string", "description": "Who owns the document"}
NEW_RELATION = {"key": "parent", "name": "Parent", "subject_resource": "folder"}
NEW_RESOURCE_ROLE = {"key": "editor", "name": "Editor", "permissions": ["read", "write"]}
DERIVED_RESOURCE_ROLE = {
    "key": "editor",
    "name": "Editor",
    "extends": ["viewer"],
    "granted_to": {
        "users_with_role": [
            {"role": "editor", "on_resource": "folder", "linked_by_relation": "parent"}
        ]
    },
}
DERIVATION_RULE = {"role": "editor", "on_resource": "folder", "linked_by_relation": "parent"}
NEW_ROLE = {"key": "admin", "name": "Admin", "permissions": ["document:read"]}
NEW_USER_SET = {"key": "us_employees", "name": "US employees", "type": "userset"}
NEW_RESOURCE_SET = {
    "key": "private_docs",
    "name": "Private documents",
    "type": "resourceset",
    "resource_id": "document",
    "conditions": {"allOf": [{"resource.private": {"equals": True}}]},
}
SET_RULE = {
    "user_set": "us_employees",
    "permission": "document:read",
    "resource_set": "private_docs",
}


class Case(NamedTuple):
    """One SDK call and the one request it must send.

    ``response`` is the JSON the server answers with, or None for a 204 with no body.
    ``model`` is what the response parses into, or None when the method returns nothing; a
    list response parses into a list of ``model``.
    """

    call: Call
    method: str
    path: str
    query: list[tuple[str, str]]
    body: Any
    response: dict[str, Any] | list[dict[str, Any]] | None
    model: type[BaseModel] | None

    @property
    def request(self) -> dict[str, Any]:
        """The request, as ``tests.utils.sent()`` shows it."""
        return {"method": self.method, "path": self.path, "query": self.query, "body": self.body}


CASES = {
    # resources
    "resources.list": Case(
        call=call("resources.list"),
        method="GET",
        path=RESOURCES,
        query=DEFAULT_PAGE,
        body=None,
        response=[RESOURCE],
        model=ResourceRead,
    ),
    "resources.list-page": Case(
        call=call("resources.list", page=2, per_page=10),
        method="GET",
        path=RESOURCES,
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ResourceRead,
    ),
    "resources.get": Case(
        call=call("resources.get", "document"),
        method="GET",
        path=DOCUMENT,
        query=[],
        body=None,
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.get_by_key": Case(
        call=call("resources.get_by_key", "document"),
        method="GET",
        path=DOCUMENT,
        query=[],
        body=None,
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.get_by_id": Case(
        call=call("resources.get_by_id", RESOURCE_ID),
        method="GET",
        path=f"{RESOURCES}/{RESOURCE_ID}",
        query=[],
        body=None,
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.create": Case(
        call=call("resources.create", ResourceCreate(**NEW_RESOURCE)),
        method="POST",
        path=RESOURCES,
        query=[],
        body=NEW_RESOURCE,
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.create-dict": Case(
        call=call("resources.create", NEW_RESOURCE),
        method="POST",
        path=RESOURCES,
        query=[],
        body=NEW_RESOURCE,
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.update": Case(
        call=call("resources.update", "document", ResourceUpdate(name="Doc")),
        method="PATCH",
        path=DOCUMENT,
        query=[],
        body={"name": "Doc"},
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.update-clears-a-field": Case(
        call=call("resources.update", "document", {"description": None}),
        method="PATCH",
        path=DOCUMENT,
        query=[],
        body={"description": None},
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.replace": Case(
        call=call("resources.replace", "document", ResourceReplace(**REPLACEMENT)),
        method="PUT",
        path=DOCUMENT,
        query=[],
        body=REPLACEMENT,
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.replace-dict": Case(
        call=call("resources.replace", "document", REPLACEMENT),
        method="PUT",
        path=DOCUMENT,
        query=[],
        body=REPLACEMENT,
        response=RESOURCE,
        model=ResourceRead,
    ),
    "resources.delete": Case(
        call=call("resources.delete", "document"),
        method="DELETE",
        path=DOCUMENT,
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    # resource_attributes
    "resource_attributes.list": Case(
        call=call("resource_attributes.list", "document"),
        method="GET",
        path=f"{DOCUMENT}/attributes",
        query=DEFAULT_PAGE,
        body=None,
        response=[ATTRIBUTE],
        model=ResourceAttributeRead,
    ),
    "resource_attributes.list-page": Case(
        call=call("resource_attributes.list", "document", page=2, per_page=10),
        method="GET",
        path=f"{DOCUMENT}/attributes",
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ResourceAttributeRead,
    ),
    "resource_attributes.get": Case(
        call=call("resource_attributes.get", "document", "owner"),
        method="GET",
        path=f"{DOCUMENT}/attributes/owner",
        query=[],
        body=None,
        response=ATTRIBUTE,
        model=ResourceAttributeRead,
    ),
    "resource_attributes.get_by_key": Case(
        call=call("resource_attributes.get_by_key", "document", "owner"),
        method="GET",
        path=f"{DOCUMENT}/attributes/owner",
        query=[],
        body=None,
        response=ATTRIBUTE,
        model=ResourceAttributeRead,
    ),
    "resource_attributes.get_by_id": Case(
        call=call("resource_attributes.get_by_id", RESOURCE_ID, ATTRIBUTE_ID),
        method="GET",
        path=f"{RESOURCES}/{RESOURCE_ID}/attributes/{ATTRIBUTE_ID}",
        query=[],
        body=None,
        response=ATTRIBUTE,
        model=ResourceAttributeRead,
    ),
    "resource_attributes.create": Case(
        call=call(
            "resource_attributes.create",
            "document",
            ResourceAttributeCreate(
                key="owner", type=AttributeType.string, description="Who owns the document"
            ),
        ),
        method="POST",
        path=f"{DOCUMENT}/attributes",
        query=[],
        body=NEW_ATTRIBUTE,
        response=ATTRIBUTE,
        model=ResourceAttributeRead,
    ),
    "resource_attributes.create-dict": Case(
        call=call("resource_attributes.create", "document", NEW_ATTRIBUTE),
        method="POST",
        path=f"{DOCUMENT}/attributes",
        query=[],
        body=NEW_ATTRIBUTE,
        response=ATTRIBUTE,
        model=ResourceAttributeRead,
    ),
    "resource_attributes.update": Case(
        call=call(
            "resource_attributes.update",
            "document",
            "owner",
            ResourceAttributeUpdate(type=AttributeType.array),
        ),
        method="PATCH",
        path=f"{DOCUMENT}/attributes/owner",
        query=[],
        body={"type": "array"},
        response=ATTRIBUTE,
        model=ResourceAttributeRead,
    ),
    "resource_attributes.update-clears-a-field": Case(
        call=call("resource_attributes.update", "document", "owner", {"description": None}),
        method="PATCH",
        path=f"{DOCUMENT}/attributes/owner",
        query=[],
        body={"description": None},
        response=ATTRIBUTE,
        model=ResourceAttributeRead,
    ),
    "resource_attributes.delete": Case(
        call=call("resource_attributes.delete", "document", "owner"),
        method="DELETE",
        path=f"{DOCUMENT}/attributes/owner",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    # resource_relations
    "resource_relations.list": Case(
        call=call("resource_relations.list", "document"),
        method="GET",
        path=f"{DOCUMENT}/relations",
        query=DEFAULT_PAGE,
        body=None,
        response=RELATION_PAGE,
        model=PaginatedResultRelationRead,
    ),
    "resource_relations.list-page": Case(
        call=call("resource_relations.list", "document", page=2, per_page=10),
        method="GET",
        path=f"{DOCUMENT}/relations",
        query=SECOND_PAGE,
        body=None,
        response={"data": [], "total_count": 1, "page_count": 1},
        model=PaginatedResultRelationRead,
    ),
    "resource_relations.get": Case(
        call=call("resource_relations.get", "document", "parent"),
        method="GET",
        path=f"{DOCUMENT}/relations/parent",
        query=[],
        body=None,
        response=RELATION,
        model=RelationRead,
    ),
    "resource_relations.get_by_key": Case(
        call=call("resource_relations.get_by_key", "document", "parent"),
        method="GET",
        path=f"{DOCUMENT}/relations/parent",
        query=[],
        body=None,
        response=RELATION,
        model=RelationRead,
    ),
    "resource_relations.get_by_id": Case(
        call=call("resource_relations.get_by_id", RESOURCE_ID, RELATION_ID),
        method="GET",
        path=f"{RESOURCES}/{RESOURCE_ID}/relations/{RELATION_ID}",
        query=[],
        body=None,
        response=RELATION,
        model=RelationRead,
    ),
    "resource_relations.create": Case(
        call=call("resource_relations.create", "document", RelationCreate(**NEW_RELATION)),
        method="POST",
        path=f"{DOCUMENT}/relations",
        query=[],
        body=NEW_RELATION,
        response=RELATION,
        model=RelationRead,
    ),
    "resource_relations.create-dict": Case(
        call=call("resource_relations.create", "document", NEW_RELATION),
        method="POST",
        path=f"{DOCUMENT}/relations",
        query=[],
        body=NEW_RELATION,
        response=RELATION,
        model=RelationRead,
    ),
    "resource_relations.delete": Case(
        call=call("resource_relations.delete", "document", "parent"),
        method="DELETE",
        path=f"{DOCUMENT}/relations/parent",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    # resource_roles
    "resource_roles.list": Case(
        call=call("resource_roles.list", "document"),
        method="GET",
        path=f"{DOCUMENT}/roles",
        query=DEFAULT_PAGE,
        body=None,
        response=[RESOURCE_ROLE],
        model=ResourceRoleRead,
    ),
    "resource_roles.list-page": Case(
        call=call("resource_roles.list", "document", page=2, per_page=10),
        method="GET",
        path=f"{DOCUMENT}/roles",
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ResourceRoleRead,
    ),
    "resource_roles.get": Case(
        call=call("resource_roles.get", "document", "editor"),
        method="GET",
        path=f"{DOCUMENT}/roles/editor",
        query=[],
        body=None,
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.get_by_key": Case(
        call=call("resource_roles.get_by_key", "document", "editor"),
        method="GET",
        path=f"{DOCUMENT}/roles/editor",
        query=[],
        body=None,
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.get_by_id": Case(
        call=call("resource_roles.get_by_id", RESOURCE_ID, ROLE_ID),
        method="GET",
        path=f"{RESOURCES}/{RESOURCE_ID}/roles/{ROLE_ID}",
        query=[],
        body=None,
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.create": Case(
        call=call("resource_roles.create", "document", ResourceRoleCreate(**NEW_RESOURCE_ROLE)),
        method="POST",
        path=f"{DOCUMENT}/roles",
        query=[],
        body=NEW_RESOURCE_ROLE,
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.create-derived-dict": Case(
        call=call("resource_roles.create", "document", DERIVED_RESOURCE_ROLE),
        method="POST",
        path=f"{DOCUMENT}/roles",
        query=[],
        body=DERIVED_RESOURCE_ROLE,
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.update": Case(
        call=call(
            "resource_roles.update",
            "document",
            "editor",
            ResourceRoleUpdate(permissions=["read"]),
        ),
        method="PATCH",
        path=f"{DOCUMENT}/roles/editor",
        query=[],
        body={"permissions": ["read"]},
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.update-clears-a-field": Case(
        call=call("resource_roles.update", "document", "editor", {"description": None}),
        method="PATCH",
        path=f"{DOCUMENT}/roles/editor",
        query=[],
        body={"description": None},
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.delete": Case(
        call=call("resource_roles.delete", "document", "editor"),
        method="DELETE",
        path=f"{DOCUMENT}/roles/editor",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    "resource_roles.assign_permissions": Case(
        call=call("resource_roles.assign_permissions", "document", "editor", ["read", "write"]),
        method="POST",
        path=f"{DOCUMENT}/roles/editor/permissions",
        query=[],
        body={"permissions": ["read", "write"]},
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.remove_permissions": Case(
        call=call("resource_roles.remove_permissions", "document", "editor", ["write"]),
        method="DELETE",
        path=f"{DOCUMENT}/roles/editor/permissions",
        query=[],
        body={"permissions": ["write"]},
        response=RESOURCE_ROLE,
        model=ResourceRoleRead,
    ),
    "resource_roles.create_role_derivation": Case(
        call=call(
            "resource_roles.create_role_derivation",
            "document",
            "editor",
            DerivedRoleRuleCreate(**DERIVATION_RULE),
        ),
        method="POST",
        path=f"{DOCUMENT}/roles/editor/implicit_grants",
        query=[],
        body=DERIVATION_RULE,
        response=DERIVATION,
        model=DerivedRoleRuleRead,
    ),
    "resource_roles.create_role_derivation-dict": Case(
        call=call(
            "resource_roles.create_role_derivation",
            "document",
            "editor",
            {**DERIVATION_RULE, "when": DERIVATION_SETTINGS},
        ),
        method="POST",
        path=f"{DOCUMENT}/roles/editor/implicit_grants",
        query=[],
        body={**DERIVATION_RULE, "when": DERIVATION_SETTINGS},
        response=DERIVATION,
        model=DerivedRoleRuleRead,
    ),
    "resource_roles.delete_role_derivation": Case(
        call=call(
            "resource_roles.delete_role_derivation",
            "document",
            "editor",
            DerivedRoleRuleDelete(**DERIVATION_RULE),
        ),
        method="DELETE",
        path=f"{DOCUMENT}/roles/editor/implicit_grants",
        query=[],
        body=DERIVATION_RULE,
        response=None,
        model=None,
    ),
    "resource_roles.delete_role_derivation-dict": Case(
        call=call("resource_roles.delete_role_derivation", "document", "editor", DERIVATION_RULE),
        method="DELETE",
        path=f"{DOCUMENT}/roles/editor/implicit_grants",
        query=[],
        body=DERIVATION_RULE,
        response=None,
        model=None,
    ),
    "resource_roles.update_role_derivation_conditions": Case(
        call=call(
            "resource_roles.update_role_derivation_conditions",
            "document",
            "editor",
            PermitBackendSchemasSchemaDerivedRoleRuleDerivationSettings(
                no_direct_roles_on_object=True
            ),
        ),
        method="PUT",
        path=f"{DOCUMENT}/roles/editor/implicit_grants/conditions",
        query=[],
        body=DERIVATION_SETTINGS,
        response=DERIVATION_SETTINGS,
        model=PermitBackendSchemasSchemaDerivedRoleRuleDerivationSettings,
    ),
    "resource_roles.update_role_derivation_conditions-dict": Case(
        call=call(
            "resource_roles.update_role_derivation_conditions",
            "document",
            "editor",
            {"no_direct_roles_on_object": False},
        ),
        method="PUT",
        path=f"{DOCUMENT}/roles/editor/implicit_grants/conditions",
        query=[],
        body={"no_direct_roles_on_object": False},
        response={"no_direct_roles_on_object": False},
        model=PermitBackendSchemasSchemaDerivedRoleRuleDerivationSettings,
    ),
    # roles
    "roles.list": Case(
        call=call("roles.list"),
        method="GET",
        path=ROLES,
        query=DEFAULT_PAGE,
        body=None,
        response=[ROLE],
        model=RoleRead,
    ),
    "roles.list-page": Case(
        call=call("roles.list", page=2, per_page=10),
        method="GET",
        path=ROLES,
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=RoleRead,
    ),
    "roles.get": Case(
        call=call("roles.get", "admin"),
        method="GET",
        path=f"{ROLES}/admin",
        query=[],
        body=None,
        response=ROLE,
        model=RoleRead,
    ),
    "roles.get_by_key": Case(
        call=call("roles.get_by_key", "admin"),
        method="GET",
        path=f"{ROLES}/admin",
        query=[],
        body=None,
        response=ROLE,
        model=RoleRead,
    ),
    "roles.get_by_id": Case(
        call=call("roles.get_by_id", ROLE_ID),
        method="GET",
        path=f"{ROLES}/{ROLE_ID}",
        query=[],
        body=None,
        response=ROLE,
        model=RoleRead,
    ),
    "roles.create": Case(
        call=call("roles.create", RoleCreate(**NEW_ROLE)),
        method="POST",
        path=ROLES,
        query=[],
        body=NEW_ROLE,
        response=ROLE,
        model=RoleRead,
    ),
    "roles.create-dict": Case(
        call=call("roles.create", {**NEW_ROLE, "extends": ["viewer"]}),
        method="POST",
        path=ROLES,
        query=[],
        body={**NEW_ROLE, "extends": ["viewer"]},
        response=ROLE,
        model=RoleRead,
    ),
    "roles.update": Case(
        call=call("roles.update", "admin", RoleUpdate(name="Administrator")),
        method="PATCH",
        path=f"{ROLES}/admin",
        query=[],
        body={"name": "Administrator"},
        response=ROLE,
        model=RoleRead,
    ),
    "roles.update-clears-a-field": Case(
        call=call("roles.update", "admin", {"description": None}),
        method="PATCH",
        path=f"{ROLES}/admin",
        query=[],
        body={"description": None},
        response=ROLE,
        model=RoleRead,
    ),
    "roles.delete": Case(
        call=call("roles.delete", "admin"),
        method="DELETE",
        path=f"{ROLES}/admin",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    "roles.assign_permissions": Case(
        call=call("roles.assign_permissions", "admin", ["document:read", "document:write"]),
        method="POST",
        path=f"{ROLES}/admin/permissions",
        query=[],
        body={"permissions": ["document:read", "document:write"]},
        response=ROLE,
        model=RoleRead,
    ),
    "roles.remove_permissions": Case(
        call=call("roles.remove_permissions", "admin", ["document:write"]),
        method="DELETE",
        path=f"{ROLES}/admin/permissions",
        query=[],
        body={"permissions": ["document:write"]},
        response=ROLE,
        model=RoleRead,
    ),
    # condition_sets
    "condition_sets.list": Case(
        call=call("condition_sets.list"),
        method="GET",
        path=CONDITION_SETS,
        query=DEFAULT_PAGE,
        body=None,
        response=[CONDITION_SET],
        model=ConditionSetRead,
    ),
    "condition_sets.list-page": Case(
        call=call("condition_sets.list", page=2, per_page=10),
        method="GET",
        path=CONDITION_SETS,
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ConditionSetRead,
    ),
    "condition_sets.get": Case(
        call=call("condition_sets.get", "us_employees"),
        method="GET",
        path=f"{CONDITION_SETS}/us_employees",
        query=[],
        body=None,
        response=CONDITION_SET,
        model=ConditionSetRead,
    ),
    "condition_sets.get_by_key": Case(
        call=call("condition_sets.get_by_key", "us_employees"),
        method="GET",
        path=f"{CONDITION_SETS}/us_employees",
        query=[],
        body=None,
        response=CONDITION_SET,
        model=ConditionSetRead,
    ),
    "condition_sets.get_by_id": Case(
        call=call("condition_sets.get_by_id", CONDITION_SET_ID),
        method="GET",
        path=f"{CONDITION_SETS}/{CONDITION_SET_ID}",
        query=[],
        body=None,
        response=CONDITION_SET,
        model=ConditionSetRead,
    ),
    "condition_sets.create": Case(
        call=call(
            "condition_sets.create",
            ConditionSetCreate(
                key="us_employees",
                name="US employees",
                type=ConditionSetType.userset,
                conditions=CONDITIONS,
            ),
        ),
        method="POST",
        path=CONDITION_SETS,
        query=[],
        body={**NEW_USER_SET, "conditions": CONDITIONS},
        response=CONDITION_SET,
        model=ConditionSetRead,
    ),
    "condition_sets.create-resource-set-dict": Case(
        call=call("condition_sets.create", NEW_RESOURCE_SET),
        method="POST",
        path=CONDITION_SETS,
        query=[],
        body=NEW_RESOURCE_SET,
        response=CONDITION_SET,
        model=ConditionSetRead,
    ),
    "condition_sets.update": Case(
        call=call(
            "condition_sets.update", "us_employees", ConditionSetUpdate(conditions=CONDITIONS)
        ),
        method="PATCH",
        path=f"{CONDITION_SETS}/us_employees",
        query=[],
        body={"conditions": CONDITIONS},
        response=CONDITION_SET,
        model=ConditionSetRead,
    ),
    "condition_sets.update-clears-a-field": Case(
        call=call("condition_sets.update", "us_employees", {"description": None}),
        method="PATCH",
        path=f"{CONDITION_SETS}/us_employees",
        query=[],
        body={"description": None},
        response=CONDITION_SET,
        model=ConditionSetRead,
    ),
    "condition_sets.delete": Case(
        call=call("condition_sets.delete", "us_employees"),
        method="DELETE",
        path=f"{CONDITION_SETS}/us_employees",
        query=[],
        body=None,
        response=None,
        model=None,
    ),
    # condition_set_rules
    "condition_set_rules.list": Case(
        call=call("condition_set_rules.list"),
        method="GET",
        path=SET_RULES,
        query=DEFAULT_PAGE,
        body=None,
        response=[RULE],
        model=ConditionSetRuleRead,
    ),
    "condition_set_rules.list-filtered": Case(
        call=call(
            "condition_set_rules.list",
            user_set_key="us_employees",
            permission_key="document:read",
            resource_set_key="private_docs",
        ),
        method="GET",
        path=SET_RULES,
        query=[
            ("page", "1"),
            ("per_page", "100"),
            ("permission", "document:read"),
            ("resource_set", "private_docs"),
            ("user_set", "us_employees"),
        ],
        body=None,
        response=[RULE],
        model=ConditionSetRuleRead,
    ),
    "condition_set_rules.list-page": Case(
        call=call("condition_set_rules.list", page=2, per_page=10),
        method="GET",
        path=SET_RULES,
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ConditionSetRuleRead,
    ),
    "condition_set_rules.create": Case(
        call=call("condition_set_rules.create", ConditionSetRuleCreate(**SET_RULE)),
        method="POST",
        path=SET_RULES,
        query=[],
        body=SET_RULE,
        response=[RULE],
        model=ConditionSetRuleRead,
    ),
    "condition_set_rules.create-dict": Case(
        call=call("condition_set_rules.create", {**SET_RULE, "is_role": False}),
        method="POST",
        path=SET_RULES,
        query=[],
        body={**SET_RULE, "is_role": False},
        response=[RULE],
        model=ConditionSetRuleRead,
    ),
    "condition_set_rules.delete": Case(
        call=call("condition_set_rules.delete", ConditionSetRuleRemove(**SET_RULE)),
        method="DELETE",
        path=SET_RULES,
        query=[],
        body=SET_RULE,
        response=None,
        model=None,
    ),
    "condition_set_rules.delete-dict": Case(
        call=call("condition_set_rules.delete", SET_RULE),
        method="DELETE",
        path=SET_RULES,
        query=[],
        body=SET_RULE,
        response=None,
        model=None,
    ),
}

# The case named after each method, for the tests that need one call per method.
BASIC_CASES = {name: case for name, case in CASES.items() if name == case.call.path}


def respond(server: HTTPServer, case: Case) -> None:
    """Make ``server`` answer the request of ``case`` with the case's response."""
    handler = server.expect_request(case.path, method=case.method)
    if case.response is None:
        handler.respond_with_data("", status=204)
    else:
        handler.respond_with_json(case.response)


def test_every_public_method_has_a_case() -> None:
    public = {
        f"{api}.{name}"
        for api, api_class in SCHEMA_APIS.items()
        for name, value in vars(api_class).items()
        if not name.startswith("_") and callable(value)
    }

    assert {case.call.path for case in CASES.values()} == public
    assert set(BASIC_CASES) == public
    assert len(public) == 52


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_request_and_response(
    httpserver: HTTPServer, config: PermitConfig, case: Case, flavour: str
) -> None:
    respond(httpserver, case)

    result = invoke(config, flavour, case.call)

    assert [sent(request) for request, _ in httpserver.log] == [case.request]
    assert [sent_headers(request) for request, _ in httpserver.log] == [JSON_HEADERS]
    if case.model is None:
        assert result is None
    elif isinstance(case.response, list):
        assert type(result) is list
        assert [type(item) for item in result] == [case.model] * len(case.response)
        assert result == [case.model.parse_obj(item) for item in case.response]
    else:
        assert type(result) is case.model
        assert result == case.model.parse_obj(case.response)


# --- API errors ------------------------------------------------------------------------

INVALID_PERMISSION = ApiError(
    400,
    error_details("INVALID_PERMISSION_FORMAT", "Invalid permission format"),
    PermitApiDetailedError,
)


def validation_error(location: list[str], message: str, error_type: str) -> ApiError:
    """The API's 422 for a request whose input at ``location`` is not valid."""
    body = {"detail": [{"loc": location, "msg": message, "type": error_type}]}
    return ApiError(422, body, PermitValidationError)


INVALID_PAGE = validation_error(
    ["query", "per_page"], "Input should be less than or equal to 100", "less_than_equal"
)
INVALID_BODY = validation_error(["body", "actions"], "Field required", "missing")

# The error each method's test answers with, by the method's name, so that each error class
# the SDK raises for an API error response is checked. Every other method gets NOT_FOUND.
METHOD_ERRORS = {
    "list": INVALID_PAGE,
    "replace": INVALID_BODY,
    "create": DUPLICATE,
    "create_role_derivation": DUPLICATE,
    "assign_permissions": INVALID_PERMISSION,
    "remove_permissions": INVALID_PERMISSION,
}
ERROR_CASES = {
    name: (case, METHOD_ERRORS.get(name.split(".")[1], NOT_FOUND))
    for name, case in BASIC_CASES.items()
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(("case", "error"), ERROR_CASES.values(), ids=ERROR_CASES.keys())
def test_an_api_error_raises_the_matching_permit_api_error(
    httpserver: HTTPServer, config: PermitConfig, case: Case, error: ApiError, flavour: str
) -> None:
    httpserver.expect_request(case.path, method=case.method).respond_with_json(
        error.body, status=error.status
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(config, flavour, case.call)

    assert type(raised.value) is error.raises
    assert raised.value.status_code == error.status
    assert raised.value.details == error.body
    assert [sent(request) for request, _ in httpserver.log] == [case.request]


# --- proxy_facts_via_pdp ---------------------------------------------------------------


@pytest.fixture
def pdp_server(httpserver_ipv4: HTTPServer) -> HTTPServer:
    """A server of its own for the PDP, so a request reaching it is told from one to the API."""
    return httpserver_ipv4


@pytest.fixture
def proxy_config(httpserver: HTTPServer, pdp_server: HTTPServer) -> PermitConfig:
    """The offline config with ``proxy_facts_via_pdp`` on and the PDP on ``pdp_server``."""
    offline = offline_config(httpserver.url_for("").rstrip("/"))
    return PermitConfig(
        token=offline.token,
        api_url=offline.api_url,
        pdp=pdp_server.url_for("").rstrip("/"),
        api_context=offline.api_context,
        proxy_facts_via_pdp=True,
        facts_sync_timeout=2.5,
        facts_sync_timeout_policy="fail",
    )


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", BASIC_CASES.values(), ids=BASIC_CASES.keys())
def test_proxy_facts_via_pdp_leaves_the_request_on_the_api(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    proxy_config: PermitConfig,
    case: Case,
    flavour: str,
) -> None:
    """Only the facts methods send their requests to the PDP; these go to the API.

    The client's wait-for-sync headers go with them, as with every request a client with
    ``proxy_facts_via_pdp`` on sends to the API (see ``test_facts_sync_offline.py``).
    """
    respond(httpserver, case)

    invoke(proxy_config, flavour, case.call)

    assert [sent(request) for request, _ in httpserver.log] == [case.request]
    assert [sent_headers(request) for request, _ in httpserver.log] == [
        {**JSON_HEADERS, "X-Wait-Timeout": "2.5", "X-Timeout-Policy": "fail"}
    ]
    assert pdp_server.log == []
