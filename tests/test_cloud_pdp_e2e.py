"""The SDK's decision calls against the hosted cloud PDP.

Each test builds its own small RBAC policy in the environment the API key belongs to: a
resource type with two actions, a role that grants one of them, a tenant where the user
has that role and a second tenant where it has none. It waits for the cloud PDP to apply
the policy, then asserts the exact answers of ``check``, ``bulk_check``,
``get_user_permissions`` (with and without a context) and ``filter_objects``.

RBAC decides on the resource type and tenant alone, so the resources these tests ask
about need not exist as resource instances.

``get_user_tenants``, ``permit.pdp_api`` and the facts methods with ``proxy_facts_via_pdp``
on need no policy: only the container PDP serves their routes, and their tests check that
the cloud PDP's 404 for each reaches the caller as the error that says so. They only read,
so they write nothing even if the cloud PDP ever serves those routes.
"""

import functools
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Final

import pytest

from permit import Permit, PermitApiError, PermitConfig, PermitConnectionError
from tests.utils import CLOUD_PDP_URL, delete_quietly, poll_for, unique_key

# conftest's `permit_cloud` fixture resolves its address as
# os.getenv("PDP_URL", CLOUD_PDP_URL), so it only reaches the cloud PDP when
# PDP_URL is unset or already points there. The jobs in
# .github/workflows/test.yml that start a PDP container set PDP_URL to it, and
# test_rbac_e2e.py already covers these decisions there. This module skips on
# the same condition the fixture uses, so it runs only against the cloud PDP and
# is reported as skipped, with the reason, everywhere else. The
# `e2e (cloud PDP)` job sets PDP_URL to the cloud PDP and fails if any test in
# this module is skipped.
CONFIGURED_PDP_URL: Final[str] = os.getenv("PDP_URL", CLOUD_PDP_URL)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not CONFIGURED_PDP_URL.startswith(CLOUD_PDP_URL),
        reason=(
            f"cloud-PDP-only test: permit_cloud is configured against {CONFIGURED_PDP_URL}, "
            f"not {CLOUD_PDP_URL}. Unset PDP_URL (or point it at the cloud PDP) to run these."
        ),
    ),
]

GRANTED_ACTION: Final[str] = "read"
DENIED_ACTION: Final[str] = "write"

# Writes go to the Permit API and reach the cloud PDP asynchronously, and the
# environment is new to it. The bound is generous because it is only reached
# when the policy never arrives; polling returns as soon as it does.
PROPAGATION_TIMEOUT: Final[float] = 120.0
POLL_INTERVAL: Final[float] = 1.0

# An answer that includes an allow is polled for rather than asserted once: the cloud PDP
# applies writes asynchronously, and one answer that reflects a write does not guarantee
# the next one will. A deny is asserted once, since no stage of propagation turns it into
# an allow.
settled = functools.partial(poll_for, timeout=PROPAGATION_TIMEOUT, interval=POLL_INTERVAL)


@dataclass(frozen=True)
class CloudPolicy:
    """The keys of one test's policy, all unique to it."""

    resource: str
    role: str
    tenant: str
    other_tenant: str
    user: str

    @property
    def granted_permission(self) -> str:
        """The permission the role grants, as the PDP names it."""
        return f"{self.resource}:{GRANTED_ACTION}"

    def resource_in(self, tenant: str, key: str | None = None) -> dict[str, Any]:
        """A resource of this policy's type in ``tenant``, optionally a single instance."""
        resource: dict[str, Any] = {"type": self.resource, "tenant": tenant}
        if key is not None:
            resource["key"] = key
        return resource


@pytest.fixture
async def cloud_policy(permit_cloud: Permit) -> AsyncIterator[CloudPolicy]:
    """Create one test's policy, wait until the cloud PDP applies it, and delete it after.

    Each delete is registered before the create it undoes, so teardown also removes an
    object whose create call failed after the API had made it, and treats the 404 for one
    it never made as success. Teardown runs in reverse order of registration.
    """
    policy = CloudPolicy(
        resource=unique_key("cloud-doc"),
        role=unique_key("cloud-reader"),
        tenant=unique_key("cloud-tenant"),
        other_tenant=unique_key("cloud-other-tenant"),
        user=unique_key("cloud-user"),
    )
    api = permit_cloud.api
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
            {"key": policy.role, "name": policy.role, "permissions": [policy.granted_permission]}
        )

        for tenant in (policy.tenant, policy.other_tenant):
            teardown.push_async_callback(
                delete_quietly,
                functools.partial(api.tenants.delete, tenant),
                f"tenant '{tenant}'",
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

        allowed = await settled(
            lambda: permit_cloud.check(
                policy.user, GRANTED_ACTION, policy.resource_in(policy.tenant)
            ),
            expected=True,
        )
        assert allowed is True, (
            f"the cloud PDP did not allow '{policy.user}' to {GRANTED_ACTION} "
            f"'{policy.resource}' in tenant '{policy.tenant}' within {PROPAGATION_TIMEOUT}s"
        )
        yield policy


async def test_check(permit_cloud: Permit, cloud_policy: CloudPolicy) -> None:
    policy = cloud_policy
    instance = policy.resource_in(policy.tenant, key="doc-1")

    allowed = await settled(
        lambda: permit_cloud.check(policy.user, GRANTED_ACTION, instance), expected=True
    )

    assert allowed is True
    assert await permit_cloud.check(policy.user, DENIED_ACTION, instance) is False
    assert (
        await permit_cloud.check(
            policy.user, GRANTED_ACTION, policy.resource_in(policy.other_tenant, key="doc-1")
        )
        is False
    )


async def test_bulk_check(permit_cloud: Permit, cloud_policy: CloudPolicy) -> None:
    policy = cloud_policy
    in_tenant = policy.resource_in(policy.tenant)
    expected = [True, False, False, True]

    decisions = await settled(
        lambda: permit_cloud.bulk_check(
            [
                {"user": policy.user, "action": GRANTED_ACTION, "resource": in_tenant},
                {"user": policy.user, "action": DENIED_ACTION, "resource": in_tenant},
                {
                    "user": policy.user,
                    "action": GRANTED_ACTION,
                    "resource": policy.resource_in(policy.other_tenant),
                },
                {
                    "user": policy.user,
                    "action": GRANTED_ACTION,
                    "resource": policy.resource_in(policy.tenant, key="doc-1"),
                },
            ]
        ),
        expected=expected,
    )

    assert decisions == expected


async def test_get_user_permissions(permit_cloud: Permit, cloud_policy: CloudPolicy) -> None:
    policy = cloud_policy

    async def tenant_grants() -> dict[str, dict[str, Any]]:
        # The tenant's attributes are left out: how a PDP renders an empty set of
        # them is not what this test is about.
        permissions = await permit_cloud.get_user_permissions(
            policy.user, tenants=[policy.tenant, policy.other_tenant]
        )
        return {
            key: {
                "tenant": entry["tenant"]["key"],
                "permissions": entry["permissions"],
                "roles": entry.get("roles"),
            }
            for key, entry in permissions.items()
        }

    # The cloud PDP also lists its built-in "tenant-association" role for a user who
    # belongs to the tenant, after the roles assigned to them.
    expected = {
        f"__tenant:{policy.tenant}": {
            "tenant": policy.tenant,
            "permissions": [policy.granted_permission],
            "roles": [policy.role, "tenant-association"],
        }
    }

    assert await settled(tenant_grants, expected=expected) == expected


async def test_get_user_permissions_with_a_context(
    permit_cloud: Permit, cloud_policy: CloudPolicy
) -> None:
    """The cloud PDP accepts a context, and RBAC, which does not read it, answers the same."""
    policy = cloud_policy

    async def tenant_permissions() -> dict[str, list[str]]:
        permissions = await permit_cloud.get_user_permissions(
            policy.user,
            tenants=[policy.tenant, policy.other_tenant],
            context={"ip": "10.0.0.1", "flags": {"beta": True, "ratio": 0.5}},
        )
        return {key: entry["permissions"] for key, entry in permissions.items()}

    expected = {f"__tenant:{policy.tenant}": [policy.granted_permission]}

    assert await settled(tenant_permissions, expected=expected) == expected


async def test_filter_objects(permit_cloud: Permit, cloud_policy: CloudPolicy) -> None:
    policy = cloud_policy
    resources = [
        policy.resource_in(policy.tenant, key="kept-1"),
        policy.resource_in(policy.other_tenant, key="dropped"),
        policy.resource_in(policy.tenant, key="kept-2"),
    ]
    expected = [resources[0], resources[2]]

    kept = await settled(
        lambda: permit_cloud.filter_objects(policy.user, GRANTED_ACTION, {}, resources),
        expected=expected,
    )

    assert kept == expected
    assert await permit_cloud.filter_objects(policy.user, DENIED_ACTION, {}, resources) == []


async def test_get_user_tenants_is_not_served(permit_cloud: Permit) -> None:
    with pytest.raises(PermitConnectionError) as raised:
        await permit_cloud.get_user_tenants(unique_key("cloud-user"))

    message = str(raised.value)
    assert "got status code 404 from the PDP" in message
    assert "only the container PDP serves /user-tenants" in message
    assert raised.value.original_error is None


async def test_pdp_api_is_not_served(permit_cloud: Permit) -> None:
    with pytest.raises(PermitApiError) as raised:
        await permit_cloud.pdp_api.role_assignments.list(user_key=unique_key("cloud-user"))

    assert type(raised.value) is PermitApiError
    assert raised.value.status_code == 404
    message = str(raised.value)
    assert "got status code 404 from the PDP" in message
    assert "only the container PDP serves GET /local/role_assignments" in message


async def test_facts_through_the_pdp_are_not_served(permit_config_cloud: PermitConfig) -> None:
    permit_config_cloud.proxy_facts_via_pdp = True
    with pytest.warns(UserWarning, match="^proxy_facts_via_pdp is on"):
        client = Permit(permit_config_cloud)

    async with client:
        with pytest.raises(PermitApiError) as raised:
            await client.api.users.get(unique_key("cloud-user"))

    assert type(raised.value) is PermitApiError
    assert raised.value.status_code == 404
    message = str(raised.value)
    assert "got status code 404 from the PDP" in message
    assert "only the container PDP serves GET /facts/users/" in message
