"""Every public facts method of ``permit.api``, and the request it sends to the facts proxy.

With ``proxy_facts_via_pdp`` on, the facts methods of the ``users``, ``tenants``,
``role_assignments``, ``resource_instances`` and ``relationship_tuples`` APIs send their
requests to the PDP's ``/facts`` routes, which only the container PDP serves, and the PDP
forwards them to the API. ``CASES`` pins the request each method sends, so the tests of what
the PDP waits on (``test_facts_sync_offline.py``) and of the cloud PDP's 404 for those routes
(``test_container_pdp_only_offline.py``) cover the same methods.
"""

from typing import Any, NamedTuple

from permit.api.relationship_tuples import RelationshipTuplesApi
from permit.api.resource_instances import ResourceInstancesApi
from permit.api.role_assignments import RoleAssignmentsApi
from permit.api.tenants import TenantsApi
from permit.api.users import UsersApi
from tests.utils import FACTS, Call, call

USER_ID = "6a1b2c3d-0000-4000-8000-000000000010"
TENANT_ID = "6a1b2c3d-0000-4000-8000-000000000020"
INSTANCE_ID = "6a1b2c3d-0000-4000-8000-000000000030"


def read(**fields: Any) -> dict[str, Any]:
    """A read model's JSON: ``fields``, and the ids and timestamps every read model has."""
    return {
        "id": "6a1b2c3d-0000-4000-8000-000000000000",
        "organization_id": "6a1b2c3d-0000-4000-8000-000000000001",
        "project_id": "6a1b2c3d-0000-4000-8000-000000000002",
        "environment_id": "6a1b2c3d-0000-4000-8000-000000000003",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        **fields,
    }


USER = read(key="alice", id=USER_ID)
TENANT = read(key="acme", name="Acme", id=TENANT_ID, last_action_at="2026-01-01T00:00:00+00:00")
ROLE_ASSIGNMENT = read(
    user="alice", role="editor", user_id=USER_ID, role_id=USER_ID, tenant_id=TENANT_ID
)
RESOURCE_INSTANCE = read(
    key="readme", resource="document", tenant="default", resource_id=USER_ID, tenant_id=TENANT_ID
)
RELATIONSHIP_TUPLE = read(
    subject="folder:docs",
    relation="parent",
    object="document:readme",
    tenant="default",
    subject_id=INSTANCE_ID,
    relation_id=INSTANCE_ID,
    tenant_id=TENANT_ID,
)


# The facts APIs, which send their requests to the PDP with proxy_facts_via_pdp on.
FACTS_APIS: dict[str, type] = {
    "users": UsersApi,
    "tenants": TenantsApi,
    "role_assignments": RoleAssignmentsApi,
    "resource_instances": ResourceInstancesApi,
    "relationship_tuples": RelationshipTuplesApi,
}

# Public methods with no case of their own: a deprecated alias calls the method named here.
ALIASES = {"tenants.add_user": "tenants.create_user"}


class Case(NamedTuple):
    """A facts method, called with ``proxy_facts_via_pdp`` on, and the one request it sends.

    ``route`` is the route the request is for, as "<METHOD> <path template>": a PDP route
    under ``/facts``, or the API route of a method that goes to the API either way.
    ``response`` is the JSON the server answers with, or None for a 204 with no body.
    """

    call: Call
    route: str
    path: str
    query: tuple[tuple[str, str], ...] = ()
    body: Any = None
    response: Any = None

    @property
    def method(self) -> str:
        """The request's HTTP method."""
        return self.route.split(" ")[0]

    @property
    def request(self) -> dict[str, Any]:
        """The request, as ``tests.utils.sent()`` shows it."""
        return {
            "method": self.method,
            "path": self.path,
            "query": list(self.query),
            "body": self.body,
        }


def page(**filters: str) -> tuple[tuple[str, str], ...]:
    """The query string of a list request for the first page, sorted as ``sent()`` sorts it."""
    return tuple(sorted({"page": "1", "per_page": "100", **filters}.items()))


EMPTY_PAGE = {"data": [], "total_count": 0}
NEW_USER = {"key": "alice"}
NEW_TENANT = {"key": "acme", "name": "Acme"}
ASSIGNMENT = {"user": "alice", "role": "editor", "tenant": "default"}
INSTANCE = {"key": "readme", "resource": "document", "tenant": "default"}
TUPLE_IDENT = {"subject": "folder:docs", "relation": "parent", "object": "document:readme"}
TUPLE = {**TUPLE_IDENT, "tenant": "default"}

CASES = {
    case.call.path.removeprefix("api."): case
    for case in [
        # users
        Case(
            call("api.users.list"), "GET /facts/users", "/facts/users", page(), response=EMPTY_PAGE
        ),
        Case(
            call("api.users.get", "alice"),
            "GET /facts/users/{user_id}",
            "/facts/users/alice",
            response=USER,
        ),
        Case(
            call("api.users.get_by_key", "alice"),
            "GET /facts/users/{user_id}",
            "/facts/users/alice",
            response=USER,
        ),
        Case(
            call("api.users.get_by_id", USER_ID),
            "GET /facts/users/{user_id}",
            f"/facts/users/{USER_ID}",
            response=USER,
        ),
        Case(
            call("api.users.create", NEW_USER),
            "POST /facts/users",
            "/facts/users",
            body=NEW_USER,
            response=USER,
        ),
        Case(
            call("api.users.update", "alice", {"first_name": "Alice"}),
            "PATCH /facts/users/{user_id}",
            "/facts/users/alice",
            body={"first_name": "Alice"},
            response=USER,
        ),
        Case(
            call("api.users.sync", NEW_USER),
            "PUT /facts/users/{user_id}",
            "/facts/users/alice",
            body=NEW_USER,
            response=USER,
        ),
        Case(
            call("api.users.delete", "alice"), "DELETE /facts/users/{user_id}", "/facts/users/alice"
        ),
        Case(
            call("api.users.bulk_create", [NEW_USER]),
            "POST /facts/bulk/users",
            "/facts/bulk/users",
            body={"operations": [NEW_USER]},
            response={},
        ),
        Case(
            call("api.users.bulk_replace", [NEW_USER]),
            "PUT /facts/bulk/users",
            "/facts/bulk/users",
            body={"operations": [NEW_USER]},
            response={},
        ),
        Case(
            call("api.users.bulk_delete", ["alice"]),
            "DELETE /facts/bulk/users",
            "/facts/bulk/users",
            body={"idents": ["alice"]},
            response={},
        ),
        Case(
            call("api.users.assign_role", ASSIGNMENT),
            "POST /facts/users/{user_id}/roles",
            "/facts/users/alice/roles",
            body={"role": "editor", "tenant": "default"},
            response=ROLE_ASSIGNMENT,
        ),
        Case(
            call("api.users.unassign_role", ASSIGNMENT),
            "DELETE /facts/users/{user_id}/roles",
            "/facts/users/alice/roles",
            body={"role": "editor", "tenant": "default"},
        ),
        Case(
            call("api.users.get_assigned_roles", "alice", tenant="default"),
            "GET /facts/role_assignments",
            "/facts/role_assignments",
            page(user="alice", tenant="default"),
            response=[],
        ),
        # tenants
        Case(call("api.tenants.list"), "GET /facts/tenants", "/facts/tenants", page(), response=[]),
        Case(
            call("api.tenants.list_tenant_users", "acme"),
            "GET /facts/tenants/{tenant_id}/users",
            "/facts/tenants/acme/users",
            page(),
            response=EMPTY_PAGE,
        ),
        # Goes to the API with or without proxy_facts_via_pdp. It carries the PDP's headers
        # all the same, as every request of a client with proxy_facts_via_pdp does; the API
        # ignores them.
        Case(
            call("api.tenants.create_user", "acme", NEW_USER),
            "POST /v2/facts/{proj_id}/{env_id}/tenants/{tenant_id}/users",
            f"{FACTS}/tenants/acme/users",
            body=NEW_USER,
            response=USER,
        ),
        Case(
            call("api.tenants.get", "acme"),
            "GET /facts/tenants/{tenant_id}",
            "/facts/tenants/acme",
            response=TENANT,
        ),
        Case(
            call("api.tenants.get_by_key", "acme"),
            "GET /facts/tenants/{tenant_id}",
            "/facts/tenants/acme",
            response=TENANT,
        ),
        Case(
            call("api.tenants.get_by_id", TENANT_ID),
            "GET /facts/tenants/{tenant_id}",
            f"/facts/tenants/{TENANT_ID}",
            response=TENANT,
        ),
        Case(
            call("api.tenants.create", NEW_TENANT),
            "POST /facts/tenants",
            "/facts/tenants",
            body=NEW_TENANT,
            response=TENANT,
        ),
        Case(
            call("api.tenants.update", "acme", {"name": "Acme Inc"}),
            "PATCH /facts/tenants/{tenant_id}",
            "/facts/tenants/acme",
            body={"name": "Acme Inc"},
            response=TENANT,
        ),
        Case(
            call("api.tenants.delete", "acme"),
            "DELETE /facts/tenants/{tenant_id}",
            "/facts/tenants/acme",
        ),
        Case(
            call("api.tenants.delete_tenant_user", "acme", "alice"),
            "DELETE /facts/tenants/{tenant_id}/users/{user_id}",
            "/facts/tenants/acme/users/alice",
        ),
        Case(
            call("api.tenants.bulk_create", [NEW_TENANT]),
            "POST /facts/bulk/tenants",
            "/facts/bulk/tenants",
            body={"operations": [NEW_TENANT]},
            response={},
        ),
        Case(
            call("api.tenants.bulk_delete", ["acme"]),
            "DELETE /facts/bulk/tenants",
            "/facts/bulk/tenants",
            body={"idents": ["acme"]},
            response={},
        ),
        # role assignments
        Case(
            call("api.role_assignments.list", user_key="alice"),
            "GET /facts/role_assignments",
            "/facts/role_assignments",
            page(user="alice"),
            response=[],
        ),
        Case(
            call("api.role_assignments.list_detailed", user_key="alice"),
            "GET /facts/role_assignments/detailed",
            "/facts/role_assignments/detailed",
            page(user="alice"),
            response=EMPTY_PAGE,
        ),
        Case(
            call("api.role_assignments.assign", ASSIGNMENT),
            "POST /facts/role_assignments",
            "/facts/role_assignments",
            body=ASSIGNMENT,
            response=ROLE_ASSIGNMENT,
        ),
        Case(
            call("api.role_assignments.unassign", ASSIGNMENT),
            "DELETE /facts/role_assignments",
            "/facts/role_assignments",
            body=ASSIGNMENT,
        ),
        Case(
            call("api.role_assignments.bulk_assign", [ASSIGNMENT]),
            "POST /facts/role_assignments/bulk",
            "/facts/role_assignments/bulk",
            body=[ASSIGNMENT],
            response={},
        ),
        Case(
            call("api.role_assignments.bulk_unassign", [ASSIGNMENT]),
            "DELETE /facts/role_assignments/bulk",
            "/facts/role_assignments/bulk",
            body=[ASSIGNMENT],
            response={},
        ),
        # resource instances
        Case(
            call("api.resource_instances.list"),
            "GET /facts/resource_instances",
            "/facts/resource_instances",
            page(),
            response=[],
        ),
        Case(
            call("api.resource_instances.list_detailed"),
            "GET /facts/resource_instances/detailed",
            "/facts/resource_instances/detailed",
            page(),
            response=EMPTY_PAGE,
        ),
        Case(
            call("api.resource_instances.get", "document:readme"),
            "GET /facts/resource_instances/{instance_id}",
            "/facts/resource_instances/document:readme",
            response=RESOURCE_INSTANCE,
        ),
        Case(
            call("api.resource_instances.get_by_key", "document:readme"),
            "GET /facts/resource_instances/{instance_id}",
            "/facts/resource_instances/document:readme",
            response=RESOURCE_INSTANCE,
        ),
        Case(
            call("api.resource_instances.get_by_id", INSTANCE_ID),
            "GET /facts/resource_instances/{instance_id}",
            f"/facts/resource_instances/{INSTANCE_ID}",
            response=RESOURCE_INSTANCE,
        ),
        Case(
            call("api.resource_instances.create", INSTANCE),
            "POST /facts/resource_instances",
            "/facts/resource_instances",
            body=INSTANCE,
            response=RESOURCE_INSTANCE,
        ),
        Case(
            call("api.resource_instances.update", "document:readme", {"attributes": {"pages": 3}}),
            "PATCH /facts/resource_instances/{instance_id}",
            "/facts/resource_instances/document:readme",
            body={"attributes": {"pages": 3}},
            response=RESOURCE_INSTANCE,
        ),
        Case(
            call("api.resource_instances.delete", "document:readme"),
            "DELETE /facts/resource_instances/{instance_id}",
            "/facts/resource_instances/document:readme",
        ),
        Case(
            call("api.resource_instances.bulk_replace", [INSTANCE]),
            "PUT /facts/bulk/resource_instances",
            "/facts/bulk/resource_instances",
            body={"operations": [INSTANCE]},
            response={},
        ),
        Case(
            call("api.resource_instances.bulk_delete", ["document:readme"]),
            "DELETE /facts/bulk/resource_instances",
            "/facts/bulk/resource_instances",
            body={"idents": ["document:readme"]},
            response={},
        ),
        # relationship tuples
        Case(
            call("api.relationship_tuples.list"),
            "GET /facts/relationship_tuples",
            "/facts/relationship_tuples",
            page(),
            response=[],
        ),
        Case(
            call("api.relationship_tuples.list_detailed"),
            "GET /facts/relationship_tuples/detailed",
            "/facts/relationship_tuples/detailed",
            page(),
            response=EMPTY_PAGE,
        ),
        Case(
            call("api.relationship_tuples.create", TUPLE),
            "POST /facts/relationship_tuples",
            "/facts/relationship_tuples",
            body=TUPLE,
            response=RELATIONSHIP_TUPLE,
        ),
        Case(
            call("api.relationship_tuples.delete", TUPLE_IDENT),
            "DELETE /facts/relationship_tuples",
            "/facts/relationship_tuples",
            body=TUPLE_IDENT,
        ),
        Case(
            call("api.relationship_tuples.bulk_create", [TUPLE]),
            "POST /facts/relationship_tuples/bulk",
            "/facts/relationship_tuples/bulk",
            body={"operations": [TUPLE]},
            response={},
        ),
        Case(
            call("api.relationship_tuples.bulk_delete", [TUPLE_IDENT]),
            "DELETE /facts/relationship_tuples/bulk",
            "/facts/relationship_tuples/bulk",
            body={"idents": [TUPLE_IDENT]},
            response={},
        ),
    ]
}


def on_pdp(case: Case) -> bool:
    """Whether the method sends its request to the PDP rather than to the API."""
    return case.route.split(" ")[1].startswith("/facts/")
