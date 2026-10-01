"""get_user_permissions() with a context, against the Permit API and a PDP (PER-16337).

Each test builds a small RBAC policy in the environment the API key belongs to: a resource
type with two actions, a role that grants one of them, a tenant where the user has that
role and a second tenant where it has none. It waits until the PDP answers
``get_user_permissions`` with the role's permission, then asks again with a context.

RBAC does not read the context, so the PDP must accept the context and answer exactly as it
does without one. What an ABAC policy makes of the context is not checked here: the ABAC
decision checks in this suite are pending PER-16209 (see test_abac_e2e.py).

Every key is unique to the run, and every delete is registered before the create it
undoes, so a test that fails part way still removes what it made. Teardown runs in
reverse order of registration, and a 404 there counts as success.
"""

import functools
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Final

import pytest

from permit import Permit
from permit.sync import Permit as SyncPermit
from tests.utils import delete_quietly, poll_for, unique_key

pytestmark = pytest.mark.e2e

GRANTED_ACTION: Final[str] = "read"
DENIED_ACTION: Final[str] = "write"
CONTEXTS: Final[list[dict[str, Any]]] = [
    {},
    {"ip": "10.0.0.1", "flags": {"beta": True, "ratio": 0.5, "unset": None}, "tags": ["a", 1]},
]

# Writes reach the PDP asynchronously. The bound is reached only when an answer never
# converges; polling returns as soon as it does.
PROPAGATION_TIMEOUT: Final[float] = 60.0
POLL_INTERVAL: Final[float] = 0.5

settled = functools.partial(poll_for, timeout=PROPAGATION_TIMEOUT, interval=POLL_INTERVAL)


@dataclass(frozen=True)
class Policy:
    """The keys of one test's policy, all unique to it."""

    resource: str
    role: str
    tenant: str
    other_tenant: str
    user: str

    @property
    def expected(self) -> dict[str, list[str]]:
        """What the PDP answers for the user in the two tenants, permissions sorted."""
        return {f"__tenant:{self.tenant}": [f"{self.resource}:{GRANTED_ACTION}"]}


@pytest.fixture
async def policy(permit: Permit) -> AsyncIterator[Policy]:
    """Create one test's policy, and delete it once the test ends."""
    policy = Policy(
        resource=unique_key("context-doc"),
        role=unique_key("context-reader"),
        tenant=unique_key("context-tenant"),
        other_tenant=unique_key("context-other-tenant"),
        user=unique_key("context-user"),
    )
    api = permit.api
    async with AsyncExitStack() as teardown:
        teardown.push_async_callback(
            delete_quietly,
            functools.partial(api.resources.delete, policy.resource),
            f"resource '{policy.resource}'",
        )
        await api.resources.create(
            {
                "key": policy.resource,
                "name": policy.resource,
                "actions": {GRANTED_ACTION: {}, DENIED_ACTION: {}},
            }
        )
        teardown.push_async_callback(
            delete_quietly,
            functools.partial(api.roles.delete, policy.role),
            f"role '{policy.role}'",
        )
        await api.roles.create(
            {
                "key": policy.role,
                "name": policy.role,
                "permissions": [f"{policy.resource}:{GRANTED_ACTION}"],
            }
        )
        for tenant in (policy.tenant, policy.other_tenant):
            teardown.push_async_callback(
                delete_quietly, functools.partial(api.tenants.delete, tenant), f"tenant '{tenant}'"
            )
            await api.tenants.create({"key": tenant, "name": tenant})
        teardown.push_async_callback(
            delete_quietly,
            functools.partial(api.users.delete, policy.user),
            f"user '{policy.user}'",
        )
        await api.users.create({"key": policy.user})
        assignment = {"user": policy.user, "role": policy.role, "tenant": policy.tenant}
        teardown.push_async_callback(
            delete_quietly,
            functools.partial(api.users.unassign_role, assignment),
            f"role assignment {assignment}",
        )
        await api.users.assign_role(assignment)
        yield policy


def permissions_by_tenant(permissions: dict[str, Any]) -> dict[str, list[str]]:
    """Each tenant's permissions, sorted; the rest of the PDP's answer is not compared."""
    return {key: sorted(entry["permissions"]) for key, entry in permissions.items()}


async def test_the_pdp_answers_with_a_context_as_without_one(
    permit: Permit, policy: Policy
) -> None:
    tenants = [policy.tenant, policy.other_tenant]

    async def granted(context: dict[str, Any] | None = None) -> dict[str, list[str]]:
        answer = await permit.get_user_permissions(policy.user, tenants, context=context)
        return permissions_by_tenant(answer)

    assert await settled(granted, expected=policy.expected) == policy.expected
    for context in CONTEXTS:
        with_context = functools.partial(granted, context)
        assert await settled(with_context, expected=policy.expected) == policy.expected, context

    # With the context store holding a base context, the merged context is accepted too.
    permit._enforcer.context_store.add({"region": "eu"})
    assert await settled(lambda: granted({"ip": "10.0.0.2"}), expected=policy.expected) == (
        policy.expected
    )


async def test_the_blocking_client_sends_the_context_too(
    sync_permit: SyncPermit, policy: Policy
) -> None:
    async def granted() -> dict[str, list[str]]:
        answer = sync_permit.get_user_permissions(
            policy.user, [policy.tenant], context=CONTEXTS[-1]
        )
        return permissions_by_tenant(answer)

    assert await settled(granted, expected=policy.expected) == policy.expected
