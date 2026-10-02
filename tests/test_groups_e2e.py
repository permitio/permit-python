"""The Groups API against the Permit API and a PDP (PER-16677).

A group is a resource instance of a group resource type. ``assign_user`` gives the user
that type's ``member`` role on the group, and ``assign_role`` grants the group a role on
one resource instance: the API links the group to that instance and derives the role
from ``member``, so the PDP grants it to every member of the group (ReBAC). A group's
role reaches its members on that instance only.

Each test builds its own policy in the environment the API key belongs to. Every key is
unique to the run, and every delete is registered before the create it undoes, so a test
that fails part way still removes what it made. Teardown runs in reverse order of
registration, and a 404 there counts as success.
"""

import functools
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, ExitStack
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import pytest

from permit import Permit
from permit.api.models import GroupAddRole, GroupAssignment, GroupRead, GroupReadSchema, UserRead
from permit.exceptions import PermitApiError
from permit.sync import Permit as SyncPermit
from tests.utils import delete_quietly, delete_quietly_blocking, poll_for, unique_key

pytestmark = pytest.mark.e2e

READ: Final[str] = "read"
VIEWER: Final[str] = "viewer"
# The role the API gives a user on the group's resource instance when it adds them to it.
MEMBER: Final[str] = "member"
# The type of a group created without one, and the type a bare group key is read as.
DEFAULT_GROUP_TYPE: Final[str] = "group"
FIRST_DOCUMENT: Final[str] = "doc-1"
SECOND_DOCUMENT: Final[str] = "doc-2"
PER_PAGE: Final[int] = 100
NOT_FOUND: Final[int] = 404
CONFLICT: Final[int] = 409

# Writes reach the PDP asynchronously, and a role a member gets through two groups
# depends on every write along the way. The bound is reached only when a decision never
# converges; polling returns as soon as it does.
PROPAGATION_TIMEOUT: Final[float] = 60.0
POLL_INTERVAL: Final[float] = 0.5

settled = functools.partial(poll_for, timeout=PROPAGATION_TIMEOUT, interval=POLL_INTERVAL)


@dataclass(frozen=True)
class GroupPolicy:
    """The keys of one test's policy, all unique to it."""

    tenant: str
    group_type: str
    document_type: str

    def group(self, key: str) -> str:
        """The group's identifier in the ``"<type>:<key>"`` form."""
        return f"{self.group_type}:{key}"

    def document(self, key: str) -> dict[str, Any]:
        """One of the policy's documents, as ``permit.check`` takes a resource."""
        return {"type": self.document_type, "key": key, "tenant": self.tenant}

    def viewer_on(self, document_key: str) -> GroupAddRole:
        """The ``viewer`` role on one of the policy's documents, for a group to be granted."""
        return GroupAddRole(
            role=VIEWER,
            resource=self.document_type,
            resource_instance=document_key,
            tenant=self.tenant,
        )


@pytest.fixture
async def teardown() -> AsyncIterator[AsyncExitStack]:
    """The deletes a test and its fixtures register, run once the test ends."""
    async with AsyncExitStack() as stack:
        yield stack


@pytest.fixture
async def group_policy(permit: Permit, teardown: AsyncExitStack) -> GroupPolicy:
    """A tenant, a group resource type, and a document type with a ``viewer`` role.

    The document type has two documents in the tenant. The tests create their groups of
    the group resource type and grant them ``viewer`` on one document or the other.
    """
    policy = GroupPolicy(
        tenant=unique_key("groups-tenant"),
        group_type=unique_key("team"),
        document_type=unique_key("groups-doc"),
    )
    api = permit.api

    teardown.push_async_callback(
        delete_quietly,
        functools.partial(api.resources.delete, policy.document_type),
        f"resource '{policy.document_type}'",
    )
    await api.resources.create(
        {
            "key": policy.document_type,
            "name": policy.document_type,
            "actions": {READ: {}},
            "roles": {VIEWER: {"name": "Viewer", "permissions": [READ]}},
        }
    )

    teardown.push_async_callback(
        delete_quietly,
        functools.partial(api.resources.delete, policy.group_type),
        f"resource '{policy.group_type}'",
    )
    await api.resources.create(
        {"key": policy.group_type, "name": policy.group_type, "actions": {READ: {}}}
    )

    teardown.push_async_callback(
        delete_quietly,
        functools.partial(api.tenants.delete, policy.tenant),
        f"tenant '{policy.tenant}'",
    )
    await api.tenants.create({"key": policy.tenant, "name": policy.tenant})

    for document_key in (FIRST_DOCUMENT, SECOND_DOCUMENT):
        document = f"{policy.document_type}:{document_key}"
        teardown.push_async_callback(
            delete_quietly,
            functools.partial(api.resource_instances.delete, document),
            f"resource instance '{document}'",
        )
        await api.resource_instances.create(
            {"key": document_key, "resource": policy.document_type, "tenant": policy.tenant}
        )
    return policy


async def create_user(permit: Permit, teardown: AsyncExitStack, name: str) -> UserRead:
    """Create a user with a unique key, its delete registered first."""
    key = unique_key(name)
    teardown.push_async_callback(
        delete_quietly, functools.partial(permit.api.users.delete, key), f"user '{key}'"
    )
    return await permit.api.users.create({"key": key})


async def create_group(
    permit: Permit,
    teardown: AsyncExitStack,
    key: str,
    *,
    tenant: str,
    group_type: str | None = None,
) -> GroupRead:
    """Create a group, its delete registered first.

    Without ``group_type`` the group is created with none, so it gets the default type.
    """
    group = f"{group_type or DEFAULT_GROUP_TYPE}:{key}"
    teardown.push_async_callback(
        delete_quietly, functools.partial(permit.api.groups.delete, group), f"group '{group}'"
    )
    group_data: dict[str, Any] = {"group_instance_key": key, "group_tenant": tenant}
    if group_type is not None:
        group_data["group_resource_type_key"] = group_type
    return await permit.api.groups.create(group_data)


async def find_group(permit: Permit, group_id: UUID) -> GroupReadSchema | None:
    """Find a group by id across every page of ``groups.list``.

    The environment is shared, so the group is not necessarily on the first page.
    """
    page = 1
    while True:
        groups = (await permit.api.groups.list(page=page, per_page=PER_PAGE)).data
        for group in groups:
            if group.id == group_id:
                return group
        if len(groups) < PER_PAGE:
            return None
        page += 1


async def memberships(permit: Permit, user_key: str, group: str) -> list[tuple[str, str | None]]:
    """The roles the user is assigned on the group's resource instance, with their tenants."""
    assignments = await permit.api.role_assignments.list(
        user_key=user_key, resource_instance_key=group
    )
    return [(assignment.role, assignment.tenant) for assignment in assignments]


def blocking_memberships(
    sync_permit: SyncPermit, user_key: str, group: str
) -> list[tuple[str, str | None]]:
    """``memberships`` through the blocking client."""
    assignments = sync_permit.api.role_assignments.list(
        user_key=user_key, resource_instance_key=group
    )
    return [(assignment.role, assignment.tenant) for assignment in assignments]


async def assert_no_group(permit: Permit, group: str) -> None:
    """Assert that ``groups.get`` answers 404 for ``group``."""
    with pytest.raises(PermitApiError) as missing:
        await permit.api.groups.get(group)
    assert missing.value.status_code == NOT_FOUND, f"group '{group}' still exists"


async def ensure_default_group_type(permit: Permit, teardown: AsyncExitStack) -> None:
    """Create the default group resource type, unless the environment already has one.

    Only a type this test created is deleted at teardown: one that was already there
    belongs to whoever made it.
    """
    try:
        await permit.api.resources.get(DEFAULT_GROUP_TYPE)
    except PermitApiError as error:
        if error.status_code != NOT_FOUND:
            raise
        teardown.push_async_callback(
            delete_quietly,
            functools.partial(permit.api.resources.delete, DEFAULT_GROUP_TYPE),
            f"resource '{DEFAULT_GROUP_TYPE}'",
        )
        await permit.api.resources.create(
            {"key": DEFAULT_GROUP_TYPE, "name": "Group", "actions": {READ: {}}}
        )


async def test_list_and_get_return_the_group(
    permit: Permit, teardown: AsyncExitStack, group_policy: GroupPolicy
) -> None:
    policy = group_policy
    key = unique_key("eng")

    created = await create_group(
        permit, teardown, key, tenant=policy.tenant, group_type=policy.group_type
    )

    assert created.group_instance_key == key
    assert created.group_resource_type_key == policy.group_type
    assert created.group_tenant == policy.tenant
    assert not created.users
    with pytest.raises(PermitApiError) as duplicate:
        await permit.api.groups.create(
            {
                "group_resource_type_key": policy.group_type,
                "group_instance_key": key,
                "group_tenant": policy.tenant,
            }
        )
    assert duplicate.value.status_code == CONFLICT

    fetched = await permit.api.groups.get(policy.group(key))
    assert fetched.group_instance_key == key
    assert fetched.group_resource_type_key == policy.group_type
    assert fetched.group_tenant == policy.tenant
    assert await permit.api.groups.get(str(fetched.id)) == fetched
    assert await find_group(permit, fetched.id) == fetched
    # A bare key is read as a group of the default type, so it does not name this group.
    await assert_no_group(permit, key)


@pytest.mark.parametrize("form", ["type:key", "id"])
async def test_a_group_is_managed_by_either_identifier(
    permit: Permit, teardown: AsyncExitStack, group_policy: GroupPolicy, form: str
) -> None:
    policy = group_policy
    key = unique_key("eng")
    group = policy.group(key)
    user = await create_user(permit, teardown, "group-member")
    await create_group(permit, teardown, key, tenant=policy.tenant, group_type=policy.group_type)
    fetched = await permit.api.groups.get(group)
    identifier = str(fetched.id) if form == "id" else group

    joined = await permit.api.groups.assign_user(identifier, user.key, policy.tenant)

    assert joined.group_instance_key == key
    assert user.id in (joined.users or [])
    assert await memberships(permit, user.key, group) == [(MEMBER, policy.tenant)]

    await permit.api.groups.remove_user(identifier, user.key, policy.tenant)

    assert await memberships(permit, user.key, group) == []

    await permit.api.groups.delete(identifier)

    await assert_no_group(permit, group)
    with pytest.raises(PermitApiError) as deleted_twice:
        await permit.api.groups.delete(identifier)
    assert deleted_twice.value.status_code == NOT_FOUND


async def test_a_bare_key_names_a_group_of_the_default_type(
    permit: Permit, teardown: AsyncExitStack
) -> None:
    tenant = unique_key("groups-tenant")
    key = unique_key("eng")
    await ensure_default_group_type(permit, teardown)
    teardown.push_async_callback(
        delete_quietly, functools.partial(permit.api.tenants.delete, tenant), f"tenant '{tenant}'"
    )
    await permit.api.tenants.create({"key": tenant, "name": tenant})
    user = await create_user(permit, teardown, "group-member")

    created = await create_group(permit, teardown, key, tenant=tenant)

    assert created.group_resource_type_key == DEFAULT_GROUP_TYPE
    by_key = await permit.api.groups.get(key)
    assert by_key.group_instance_key == key
    assert by_key.group_resource_type_key == DEFAULT_GROUP_TYPE
    assert await permit.api.groups.get(f"{DEFAULT_GROUP_TYPE}:{key}") == by_key
    assert await permit.api.groups.get(str(by_key.id)) == by_key

    joined = await permit.api.groups.assign_user(key, user.key, tenant)

    assert user.id in (joined.users or [])
    group = f"{DEFAULT_GROUP_TYPE}:{key}"
    assert await memberships(permit, user.key, group) == [(MEMBER, tenant)]

    await permit.api.groups.remove_user(key, user.key, tenant)

    assert await memberships(permit, user.key, group) == []

    await permit.api.groups.delete(key)

    await assert_no_group(permit, group)


async def test_a_role_granted_to_a_group_reaches_its_members(
    permit: Permit, teardown: AsyncExitStack, group_policy: GroupPolicy
) -> None:
    policy = group_policy
    groups = permit.api.groups
    key = unique_key("eng")
    group = policy.group(key)
    member = await create_user(permit, teardown, "group-member")
    outsider = await create_user(permit, teardown, "group-outsider")
    await create_group(permit, teardown, key, tenant=policy.tenant, group_type=policy.group_type)
    first, second = policy.document(FIRST_DOCUMENT), policy.document(SECOND_DOCUMENT)

    granted = await groups.assign_role(group, policy.viewer_on(FIRST_DOCUMENT))
    joined = await groups.assign_user(group, member.key, policy.tenant)

    assert f"{policy.document_type}:{FIRST_DOCUMENT}#{VIEWER}" in (granted.assigned_roles or [])
    assert member.id in (joined.users or [])
    allowed = await settled(lambda: permit.check(member.key, READ, first), expected=True)
    assert allowed is True, f"'{member.key}' never got the group's role on {first}"
    # The role holds on the instance the group was granted it on, for the group's
    # members: not on the type's other document, and not for a user outside the group.
    assert await permit.check(member.key, READ, second) is False
    assert await permit.check(outsider.key, READ, first) is False

    await groups.remove_user(group, member.key, policy.tenant)

    allowed = await settled(lambda: permit.check(member.key, READ, first), expected=False)
    assert allowed is False, f"'{member.key}' kept the group's role after leaving it"

    await groups.assign_user(group, member.key, policy.tenant)
    allowed = await settled(lambda: permit.check(member.key, READ, first), expected=True)
    assert allowed is True, f"'{member.key}' did not get the group's role back on rejoining"

    await groups.remove_role(group, policy.viewer_on(FIRST_DOCUMENT))

    allowed = await settled(lambda: permit.check(member.key, READ, first), expected=False)
    assert allowed is False, f"'{member.key}' kept a role the group no longer has"


async def test_assign_group_makes_the_group_a_member_of_the_other(
    permit: Permit, teardown: AsyncExitStack, group_policy: GroupPolicy
) -> None:
    policy = group_policy
    groups = permit.api.groups
    inner_key, outer_key = unique_key("backend"), unique_key("engineering")
    inner, outer = policy.group(inner_key), policy.group(outer_key)
    inner_member = await create_user(permit, teardown, "inner-member")
    outer_member = await create_user(permit, teardown, "outer-member")
    for key in (inner_key, outer_key):
        await create_group(
            permit, teardown, key, tenant=policy.tenant, group_type=policy.group_type
        )
    first, second = policy.document(FIRST_DOCUMENT), policy.document(SECOND_DOCUMENT)
    await groups.assign_role(outer, policy.viewer_on(FIRST_DOCUMENT))
    await groups.assign_role(inner, policy.viewer_on(SECOND_DOCUMENT))
    await groups.assign_user(outer, outer_member.key, policy.tenant)
    await groups.assign_user(inner, inner_member.key, policy.tenant)

    nested = await groups.assign_group(inner, GroupAssignment(group_instance_key=outer_key))

    assert nested.group_instance_key == inner_key
    # The members of the group in the path become members of the group in the body, so
    # they get its roles and keep their own.
    allowed = await settled(lambda: permit.check(inner_member.key, READ, first), expected=True)
    assert allowed is True, f"'{inner_member.key}' never got the outer group's role"
    allowed = await settled(lambda: permit.check(inner_member.key, READ, second), expected=True)
    assert allowed is True, f"'{inner_member.key}' lost the inner group's own role"
    # The other way round, nothing: the outer group's members do not get the inner
    # group's role. That role has reached the PDP (checked just above), and so has the
    # outer member's own one (checked here first).
    allowed = await settled(lambda: permit.check(outer_member.key, READ, first), expected=True)
    assert allowed is True, f"'{outer_member.key}' never got the outer group's role"
    assert await permit.check(outer_member.key, READ, second) is False

    with pytest.raises(PermitApiError) as duplicate:
        await groups.assign_group(inner, {"group_instance_key": outer_key})
    assert duplicate.value.status_code == CONFLICT
    # The group in the body is looked up by its instance key or id among groups of the
    # path group's type; the "<type>:<key>" form names none of them.
    with pytest.raises(PermitApiError) as type_and_key:
        await groups.assign_group(inner, {"group_instance_key": outer})
    assert type_and_key.value.status_code == NOT_FOUND

    await groups.remove_group(inner, GroupAssignment(group_instance_key=outer_key))

    allowed = await settled(lambda: permit.check(inner_member.key, READ, first), expected=False)
    assert allowed is False, f"'{inner_member.key}' kept the outer group's role"
    assert await permit.check(inner_member.key, READ, second) is True


def test_the_blocking_client_manages_a_group(sync_permit: SyncPermit) -> None:
    api = sync_permit.api
    tenant = unique_key("groups-tenant")
    group_type = unique_key("team")
    key = unique_key("eng")
    group = f"{group_type}:{key}"
    user_key = unique_key("group-member")
    with ExitStack() as teardown:
        teardown.callback(
            delete_quietly_blocking,
            functools.partial(api.resources.delete, group_type),
            f"resource '{group_type}'",
        )
        api.resources.create({"key": group_type, "name": group_type, "actions": {READ: {}}})
        teardown.callback(
            delete_quietly_blocking,
            functools.partial(api.tenants.delete, tenant),
            f"tenant '{tenant}'",
        )
        api.tenants.create({"key": tenant, "name": tenant})
        teardown.callback(
            delete_quietly_blocking,
            functools.partial(api.users.delete, user_key),
            f"user '{user_key}'",
        )
        user = api.users.create({"key": user_key})
        teardown.callback(
            delete_quietly_blocking, functools.partial(api.groups.delete, group), f"group '{group}'"
        )

        created = api.groups.create(
            {
                "group_resource_type_key": group_type,
                "group_instance_key": key,
                "group_tenant": tenant,
            }
        )

        assert created.group_instance_key == key
        fetched = api.groups.get(group)
        assert fetched.group_instance_key == key
        assert fetched.group_resource_type_key == group_type
        assert fetched.group_tenant == tenant
        joined = api.groups.assign_user(group, user_key, tenant)
        assert user.id in (joined.users or [])
        assert blocking_memberships(sync_permit, user_key, group) == [(MEMBER, tenant)]
        api.groups.remove_user(group, user_key, tenant)
        assert blocking_memberships(sync_permit, user_key, group) == []
        api.groups.delete(group)
        with pytest.raises(PermitApiError) as missing:
            api.groups.get(group)
        assert missing.value.status_code == NOT_FOUND
