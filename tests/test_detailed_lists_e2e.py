"""The detailed lists against the Permit API (PER-16337).

``list_detailed()`` on ``role_assignments``, ``resource_instances`` and
``relationship_tuples`` reads the API's ``/detailed`` routes. Each test builds one small
policy in the environment the API key belongs to: a tenant, a folder resource type, a
document resource type whose ``parent`` relation points at folders and which has a
``viewer`` resource role, a tenant role, a user, one folder and one document in the tenant,
the tuple that makes the folder the document's parent, and two role assignments for the
user (the tenant role, and ``viewer`` on the document).

Every key is unique to the run, and every delete is registered before the create it
undoes, so a test that fails part way still removes what it made. Teardown runs in
reverse order of registration, and a 404 there counts as success. The lists are filtered
to the test's own objects, since the environment is shared.
"""

import functools
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Final

import pytest

from permit import Permit
from permit.api.models import RelationshipTupleBlockRead
from permit.sync import Permit as SyncPermit
from tests.utils import delete_quietly, unique_key

pytestmark = pytest.mark.e2e

READ: Final[str] = "read"
VIEWER: Final[str] = "viewer"
PARENT: Final[str] = "parent"
FOLDER_KEY: Final[str] = "docs"
DOCUMENT_KEY: Final[str] = "readme"
TENANT_ATTRIBUTES: Final[dict[str, str]] = {"tier": "gold"}
USER_ATTRIBUTES: Final[dict[str, str]] = {"department": "eng"}
DOCUMENT_ATTRIBUTES: Final[dict[str, bool]] = {"public": False}


@dataclass(frozen=True)
class Policy:
    """The keys of one test's policy, all unique to it."""

    tenant: str
    folder_type: str
    document_type: str
    role: str
    user: str

    @property
    def folder(self) -> str:
        return f"{self.folder_type}:{FOLDER_KEY}"

    @property
    def document(self) -> str:
        return f"{self.document_type}:{DOCUMENT_KEY}"

    @property
    def email(self) -> str:
        return f"{self.user}@example.com"


@pytest.fixture
async def policy(permit: Permit) -> AsyncIterator[Policy]:
    """Create one test's policy, and delete it once the test ends."""
    policy = Policy(
        tenant=unique_key("detailed-tenant"),
        folder_type=unique_key("detailed-folder"),
        document_type=unique_key("detailed-doc"),
        role=unique_key("detailed-reader"),
        user=unique_key("detailed-user"),
    )
    api = permit.api
    async with AsyncExitStack() as teardown:

        def on_teardown(delete: Callable[[], Awaitable[None]], description: str) -> None:
            teardown.push_async_callback(delete_quietly, delete, f"'{description}'")

        on_teardown(functools.partial(api.tenants.delete, policy.tenant), policy.tenant)
        await api.tenants.create(
            {
                "key": policy.tenant,
                "name": f"Tenant {policy.tenant}",
                "attributes": TENANT_ATTRIBUTES,
            }
        )
        on_teardown(functools.partial(api.resources.delete, policy.folder_type), policy.folder_type)
        await api.resources.create(
            {"key": policy.folder_type, "name": policy.folder_type, "actions": {READ: {}}}
        )
        on_teardown(
            functools.partial(api.resources.delete, policy.document_type), policy.document_type
        )
        await api.resources.create(
            {
                "key": policy.document_type,
                "name": policy.document_type,
                "actions": {READ: {}},
                "roles": {VIEWER: {"name": "Viewer", "permissions": [READ]}},
                "relations": {PARENT: policy.folder_type},
            }
        )
        on_teardown(functools.partial(api.roles.delete, policy.role), policy.role)
        await api.roles.create(
            {
                "key": policy.role,
                "name": f"Role {policy.role}",
                "permissions": [f"{policy.document_type}:{READ}"],
            }
        )
        on_teardown(functools.partial(api.users.delete, policy.user), policy.user)
        await api.users.create(
            {
                "key": policy.user,
                "email": policy.email,
                "first_name": "Ada",
                "attributes": USER_ATTRIBUTES,
            }
        )
        on_teardown(functools.partial(api.resource_instances.delete, policy.folder), policy.folder)
        await api.resource_instances.create(
            {"key": FOLDER_KEY, "resource": policy.folder_type, "tenant": policy.tenant}
        )
        on_teardown(
            functools.partial(api.resource_instances.delete, policy.document), policy.document
        )
        await api.resource_instances.create(
            {
                "key": DOCUMENT_KEY,
                "resource": policy.document_type,
                "tenant": policy.tenant,
                "attributes": DOCUMENT_ATTRIBUTES,
            }
        )
        relationship = {
            "subject": policy.folder,
            "relation": PARENT,
            "object": policy.document,
            "tenant": policy.tenant,
        }
        # The delete body names the tuple by subject, relation and object; the API
        # rejects a tenant there with a 422.
        unrelate = {key: relationship[key] for key in ("subject", "relation", "object")}
        on_teardown(functools.partial(api.relationship_tuples.delete, unrelate), str(unrelate))
        await api.relationship_tuples.create(relationship)
        for assignment in (
            {"user": policy.user, "role": policy.role, "tenant": policy.tenant},
            {
                "user": policy.user,
                "role": VIEWER,
                "tenant": policy.tenant,
                "resource_instance": policy.document,
            },
        ):
            on_teardown(
                functools.partial(api.role_assignments.unassign, assignment), str(assignment)
            )
            await api.role_assignments.assign(assignment)
        yield policy


async def test_role_assignments_list_detailed_names_the_role_user_tenant_and_instance(
    permit: Permit, policy: Policy
) -> None:
    role_assignments = permit.api.role_assignments

    page = await role_assignments.list_detailed(user_key=policy.user)

    assert page.total_count == 2
    by_role = {assignment.role.key: assignment for assignment in page.data}
    assert set(by_role) == {policy.role, VIEWER}
    for assignment in page.data:
        assert (assignment.user.key, assignment.user.email) == (policy.user, policy.email)
        assert assignment.user.first_name == "Ada"
        assert assignment.user.attributes == USER_ATTRIBUTES
        assert (assignment.tenant.key, assignment.tenant.name) == (
            policy.tenant,
            f"Tenant {policy.tenant}",
        )
        assert assignment.tenant.attributes == TENANT_ATTRIBUTES
    tenant_role = by_role[policy.role]
    assert tenant_role.role.name == f"Role {policy.role}"
    assert tenant_role.resource_instance is None
    resource_role = by_role[VIEWER]
    assert resource_role.role.name == "Viewer"
    assert resource_role.resource_instance is not None
    assert (resource_role.resource_instance.resource, resource_role.resource_instance.key) == (
        policy.document_type,
        DOCUMENT_KEY,
    )
    assert resource_role.resource_instance.attributes == DOCUMENT_ATTRIBUTES

    # The same assignments as list() returns for the same filter, by id.
    listed = await role_assignments.list(user_key=policy.user)
    assert {assignment.id for assignment in listed} == {assignment.id for assignment in page.data}

    on_instance = await role_assignments.list_detailed(
        user_key=policy.user, tenant_key=policy.tenant, resource_instance_key=policy.document
    )
    assert [assignment.role.key for assignment in on_instance.data] == [VIEWER]
    assert on_instance.total_count == 1

    first = await role_assignments.list_detailed(user_key=policy.user, per_page=1)
    second = await role_assignments.list_detailed(user_key=policy.user, page=2, per_page=1)
    assert (first.total_count, len(first.data), len(second.data)) == (2, 1, 1)
    assert {first.data[0].role.key, second.data[0].role.key} == {policy.role, VIEWER}


async def test_resource_instances_list_detailed_lists_each_instances_relationships(
    permit: Permit, policy: Policy
) -> None:
    resource_instances = permit.api.resource_instances
    relationship = RelationshipTupleBlockRead(
        subject=policy.folder, relation=PARENT, object=policy.document
    )

    documents = await resource_instances.list_detailed(
        resource_key=policy.document_type, tenant_key=policy.tenant
    )
    folders = await resource_instances.list_detailed(
        resource_key=policy.folder_type, tenant_key=policy.tenant
    )

    assert documents.total_count == 1
    (document,) = documents.data
    assert (document.key, document.resource, document.tenant) == (
        DOCUMENT_KEY,
        policy.document_type,
        policy.tenant,
    )
    assert document.attributes == DOCUMENT_ATTRIBUTES
    assert document.relationships == [relationship]
    assert folders.total_count == 1
    (folder,) = folders.data
    assert folder.key == FOLDER_KEY
    assert folder.relationships == [relationship]

    # The detailed search matches a key exactly, where list() also matches part of one.
    exact = await resource_instances.list_detailed(
        resource_key=policy.document_type, search_key=DOCUMENT_KEY
    )
    assert [instance.key for instance in exact.data] == [DOCUMENT_KEY]
    partial = await resource_instances.list_detailed(
        resource_key=policy.document_type, search_key=DOCUMENT_KEY[:-1]
    )
    assert (partial.total_count, partial.data) == (0, [])


async def test_relationship_tuples_list_detailed_fills_in_the_details(
    permit: Permit, policy: Policy
) -> None:
    relationship_tuples = permit.api.relationship_tuples

    page = await relationship_tuples.list_detailed(
        subject_key=policy.folder, tenant_key=policy.tenant
    )

    assert page.total_count == 1
    (detailed,) = page.data
    assert (detailed.subject, detailed.relation, detailed.object, detailed.tenant) == (
        policy.folder,
        PARENT,
        policy.document,
        policy.tenant,
    )
    assert detailed.subject_details is not None
    assert (detailed.subject_details.resource, detailed.subject_details.key) == (
        policy.folder_type,
        FOLDER_KEY,
    )
    assert detailed.object_details is not None
    assert (detailed.object_details.resource, detailed.object_details.key) == (
        policy.document_type,
        DOCUMENT_KEY,
    )
    assert detailed.object_details.attributes == DOCUMENT_ATTRIBUTES
    assert detailed.relation_details is not None
    assert detailed.relation_details.key == PARENT
    assert detailed.tenant_details is not None
    assert (detailed.tenant_details.key, detailed.tenant_details.name) == (
        policy.tenant,
        f"Tenant {policy.tenant}",
    )
    assert detailed.tenant_details.attributes == TENANT_ATTRIBUTES

    # The same tuple as list() returns for the same filter, where list() leaves the
    # details out.
    (listed,) = await relationship_tuples.list(subject_key=policy.folder, tenant_key=policy.tenant)
    assert listed.id == detailed.id
    assert listed.subject_details is None

    by_object = await relationship_tuples.list_detailed(
        object_key=policy.document, relation_key=PARENT
    )
    assert [found.id for found in by_object.data] == [detailed.id]


async def test_the_blocking_client_lists_the_same_detailed_pages(
    permit: Permit, sync_permit: SyncPermit, policy: Policy
) -> None:
    """The blocking client sends the same requests, so it gets the same pages back."""
    pages = (
        (
            await permit.api.role_assignments.list_detailed(user_key=policy.user),
            sync_permit.api.role_assignments.list_detailed(user_key=policy.user),
        ),
        (
            await permit.api.resource_instances.list_detailed(tenant_key=policy.tenant),
            sync_permit.api.resource_instances.list_detailed(tenant_key=policy.tenant),
        ),
        (
            await permit.api.relationship_tuples.list_detailed(tenant_key=policy.tenant),
            sync_permit.api.relationship_tuples.list_detailed(tenant_key=policy.tenant),
        ),
    )

    for awaited, blocking in pages:
        assert type(blocking) is type(awaited)
        assert blocking.total_count == awaited.total_count
        assert sorted(item.id for item in blocking.data) == sorted(item.id for item in awaited.data)
    assert [awaited.total_count for awaited, _ in pages] == [2, 2, 1]
