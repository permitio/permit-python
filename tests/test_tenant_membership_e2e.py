"""Tenant membership against the Permit API and a container PDP (PER-16678).

``tenants.add_user`` creates a user as a member of one tenant, with no role there. The
user must be new: the API answers 409 for a key that already exists, so it does not add
an existing user to another tenant. ``tenants.delete_tenant_user`` takes the user out of
the tenant, with every role they hold there.

``get_user_tenants`` asks the PDP for the user's tenants. The PDP lists the tenants in
which the user holds a role assigned in the tenant, with each tenant's attributes; a
member with no role in a tenant is not listed. Only a container PDP serves the route, so
the tests that call it skip when the PDP in use is the hosted cloud PDP.

Each test makes its own tenants, role and user in the environment the API key belongs to.
Every key is unique to the run, and every delete is registered before the create it
undoes, so a test that fails part way still removes what it made. Teardown runs in
reverse order of registration, and a 404 there counts as success.
"""

import functools
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, ExitStack
from typing import Any, Final, TypeVar

import pytest

from permit import Permit, PermitConfig, User, UserCreate, UserRead
from permit.exceptions import PermitApiError
from permit.sync import Permit as SyncPermit
from tests.utils import (
    CLOUD_PDP_URL,
    delete_quietly,
    delete_quietly_blocking,
    poll_for,
    unique_key,
)

pytestmark = pytest.mark.e2e

NOT_FOUND: Final[int] = 404
CONFLICT: Final[int] = 409
REGION: Final[dict[str, Any]] = {"region": "eu"}

# Writes reach the PDP asynchronously. The bound is reached only when an answer never
# converges; polling returns as soon as it does.
PROPAGATION_TIMEOUT: Final[float] = 60.0
POLL_INTERVAL: Final[float] = 0.5

settled = functools.partial(poll_for, timeout=PROPAGATION_TIMEOUT, interval=POLL_INTERVAL)

T = TypeVar("T")


@pytest.fixture
def container_pdp(permit_config: PermitConfig) -> None:
    """Skip the test when the PDP the ``permit`` fixtures call is the hosted cloud PDP.

    The cloud PDP answers 404 for ``get_user_tenants``. The CI jobs that run this module
    start a container PDP and point PDP_URL at it.
    """
    if permit_config.pdp.startswith(CLOUD_PDP_URL):
        pytest.skip(
            f"container-PDP-only test: the PDP in use is the cloud PDP ({permit_config.pdp}), "
            "which does not serve get_user_tenants. Point PDP_URL at a container PDP."
        )


@pytest.fixture
async def teardown() -> AsyncIterator[AsyncExitStack]:
    """The deletes a test registers, run once the test ends."""
    async with AsyncExitStack() as stack:
        yield stack


async def create_tenant(
    permit: Permit, teardown: AsyncExitStack, name: str, attributes: dict[str, Any] | None = None
) -> str:
    """Create a tenant with a unique key, its delete registered first, and return the key."""
    key = unique_key(name)
    teardown.push_async_callback(
        delete_quietly, functools.partial(permit.api.tenants.delete, key), f"tenant '{key}'"
    )
    tenant: dict[str, Any] = {"key": key, "name": key}
    if attributes is not None:
        tenant["attributes"] = attributes
    await permit.api.tenants.create(tenant)
    return key


async def create_role(permit: Permit, teardown: AsyncExitStack) -> str:
    """Create a role with a unique key, its delete registered first, and return the key."""
    key = unique_key("member-role")
    teardown.push_async_callback(
        delete_quietly, functools.partial(permit.api.roles.delete, key), f"role '{key}'"
    )
    await permit.api.roles.create({"key": key, "name": key})
    return key


def register_user_delete(permit: Permit, teardown: AsyncExitStack, user_key: str) -> None:
    """Register the delete of a user that ``add_user`` is about to create."""
    teardown.push_async_callback(
        delete_quietly, functools.partial(permit.api.users.delete, user_key), f"user '{user_key}'"
    )


async def assign_role(
    permit: Permit, teardown: AsyncExitStack, user_key: str, role: str, tenant: str
) -> None:
    """Give the user a role in the tenant, its removal registered first."""
    assignment = {"user": user_key, "role": role, "tenant": tenant}
    teardown.push_async_callback(
        delete_quietly,
        functools.partial(permit.api.users.unassign_role, assignment),
        f"role assignment {assignment}",
    )
    await permit.api.users.assign_role(assignment)


def tenant_roles(user: UserRead) -> list[tuple[str, list[str]]]:
    """The tenants the API lists the user in, each with the roles the user holds there."""
    return [(tenant.tenant, tenant.roles) for tenant in user.associated_tenants or []]


async def tenants_of(
    permit: Permit, user: User, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """What ``get_user_tenants`` answers for the user, as ``{tenant key: attributes}``.

    A mapping, because the order the PDP lists the tenants in is not part of the answer.
    """
    tenants = await permit.get_user_tenants(user, context=context)
    return {tenant.key: tenant.attributes for tenant in tenants}


def poll_for_blocking(fetch: Callable[[], T], expected: T) -> T:
    """``poll_for`` for the blocking client, with this module's bounds."""
    deadline = time.monotonic() + PROPAGATION_TIMEOUT
    answer = fetch()
    while answer != expected and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        answer = fetch()
    return answer


async def test_add_user_creates_a_member_with_no_role(
    permit: Permit, teardown: AsyncExitStack
) -> None:
    tenants = permit.api.tenants
    tenant = await create_tenant(permit, teardown, "member-tenant")
    other_tenant = await create_tenant(permit, teardown, "other-tenant")
    user_key = unique_key("member")
    register_user_delete(permit, teardown, user_key)

    member = await tenants.add_user(
        tenant,
        UserCreate(
            key=user_key,
            email=f"{user_key}@example.com",
            first_name="Ada",
            last_name="Lovelace",
            attributes={"department": "eng"},
        ),
    )

    assert member.key == user_key
    assert member.email == f"{user_key}@example.com"
    assert (member.first_name, member.last_name) == ("Ada", "Lovelace")
    assert member.attributes == {"department": "eng"}
    assert tenant_roles(member) == [(tenant, [])]
    assert member.roles == []
    listed = await tenants.list_tenant_users(tenant)
    assert [(user.key, tenant_roles(user), user.roles) for user in listed.data] == [
        (user_key, [(tenant, [])], [])
    ]
    assert listed.total_count == 1
    assert (await tenants.list_tenant_users(other_tenant)).data == []

    # The API creates the user, so a key that already exists is refused rather than added
    # to the other tenant.
    with pytest.raises(PermitApiError) as existing_user:
        await tenants.add_user(other_tenant, {"key": user_key})
    assert existing_user.value.status_code == CONFLICT
    assert (await tenants.list_tenant_users(other_tenant)).data == []

    missing_tenant = unique_key("missing-tenant")
    unadded_key = unique_key("member")
    register_user_delete(permit, teardown, unadded_key)
    with pytest.raises(PermitApiError) as no_tenant:
        await tenants.add_user(missing_tenant, {"key": unadded_key})
    assert no_tenant.value.status_code == NOT_FOUND

    await tenants.delete_tenant_user(tenant, user_key)

    assert (await tenants.list_tenant_users(tenant)).data == []
    with pytest.raises(PermitApiError) as removed_twice:
        await tenants.delete_tenant_user(tenant, user_key)
    assert removed_twice.value.status_code == NOT_FOUND


@pytest.mark.usefixtures("container_pdp")
async def test_get_user_tenants_lists_the_tenants_the_user_holds_a_role_in(
    permit: Permit, teardown: AsyncExitStack
) -> None:
    member_tenant = await create_tenant(permit, teardown, "member-tenant", attributes=REGION)
    role_tenant = await create_tenant(permit, teardown, "role-tenant")
    outside_tenant = await create_tenant(permit, teardown, "outside-tenant")
    role = await create_role(permit, teardown)
    user_key = unique_key("member")
    register_user_delete(permit, teardown, user_key)
    answered: set[str] = set()

    async def user_tenants(
        user: User = user_key, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        tenants = await tenants_of(permit, user, context)
        answered.update(tenants)
        return tenants

    await permit.api.tenants.add_user(member_tenant, {"key": user_key})
    await assign_role(permit, teardown, user_key, role, role_tenant)

    # The user is a member of both tenants, and holds a role in one of them only.
    expected: dict[str, Any] = {role_tenant: {}}
    assert await settled(user_tenants, expected=expected) == expected

    await assign_role(permit, teardown, user_key, role, member_tenant)

    expected = {member_tenant: REGION, role_tenant: {}}
    assert await settled(user_tenants, expected=expected) == expected
    # The answer depends on the user's key alone: the user's attributes and the query's
    # context do not change it.
    with_attributes: dict[str, Any] = {"key": user_key, "attributes": {"department": "eng"}}
    assert await settled(lambda: user_tenants(with_attributes), expected=expected) == expected
    assert (
        await settled(lambda: user_tenants(user_key, {"source": "e2e"}), expected=expected)
        == expected
    )

    await permit.api.tenants.delete_tenant_user(member_tenant, user_key)

    expected = {role_tenant: {}}
    assert await settled(user_tenants, expected=expected) == expected

    await permit.api.tenants.delete_tenant_user(role_tenant, user_key)

    expected = {}
    assert await settled(user_tenants, expected=expected) == expected
    assert outside_tenant not in answered


@pytest.mark.usefixtures("container_pdp")
def test_the_blocking_client_adds_a_member_and_lists_their_tenants(
    sync_permit: SyncPermit,
) -> None:
    api = sync_permit.api
    tenant = unique_key("member-tenant")
    role = unique_key("member-role")
    user_key = unique_key("member")

    def user_tenants() -> dict[str, Any]:
        return {found.key: found.attributes for found in sync_permit.get_user_tenants(user_key)}

    with ExitStack() as teardown:
        teardown.callback(
            delete_quietly_blocking,
            functools.partial(api.tenants.delete, tenant),
            f"tenant '{tenant}'",
        )
        api.tenants.create({"key": tenant, "name": tenant, "attributes": REGION})
        teardown.callback(
            delete_quietly_blocking, functools.partial(api.roles.delete, role), f"role '{role}'"
        )
        api.roles.create({"key": role, "name": role})
        teardown.callback(
            delete_quietly_blocking,
            functools.partial(api.users.delete, user_key),
            f"user '{user_key}'",
        )

        member = api.tenants.add_user(tenant, {"key": user_key})

        assert member.key == user_key
        assert tenant_roles(member) == [(tenant, [])]
        assignment = {"user": user_key, "role": role, "tenant": tenant}
        teardown.callback(
            delete_quietly_blocking,
            functools.partial(api.users.unassign_role, assignment),
            f"role assignment {assignment}",
        )
        api.users.assign_role(assignment)
        listed = api.tenants.list_tenant_users(tenant)
        assert [(user.key, tenant_roles(user)) for user in listed.data] == [
            (user_key, [(tenant, [role])])
        ]
        expected: dict[str, Any] = {tenant: REGION}
        assert poll_for_blocking(user_tenants, expected) == expected

        api.tenants.delete_tenant_user(tenant, user_key)

        assert api.tenants.list_tenant_users(tenant).data == []
        expected = {}
        assert poll_for_blocking(user_tenants, expected) == expected
