import asyncio
from typing import Awaitable, Callable, List, TypeVar

import pytest
from loguru import logger
from tests.utils import handle_cleanup_error, unique_key

from permit import ActionBlockEditable, Permit, ResourceCreate
from permit.exceptions import PermitApiDetailedError, PermitApiError

pytestmark = pytest.mark.e2e

# The whole e2e suite shares a single Permit environment, so every object this
# module creates is namespaced under one prefix. That keeps the keys collision
# proof and -- just as important -- lets the list assertions below be scoped to
# the objects this test itself created instead of counting the environment.
TEST_PREFIX = unique_key("roles-async")
TEST_RESOURCE_KEY = f"{TEST_PREFIX}-resource"
TEST_ADMIN_ROLE_KEY = f"{TEST_PREFIX}-testadmin"
TEST_EMPTY_ROLE_KEY = f"{TEST_PREFIX}-emptyrole"
# The urn is unique per resource server-side, so a fixed urn collides across
# runs and reports the clash against the *key*, which reads like a key clash.
TEST_RESOURCE_URN = f"prn:gdrive:{TEST_PREFIX}"

TPropagated = TypeVar("TPropagated")

# The API indexes a resource's actions asynchronously, so for a short window
# after the resource is created a role that references `<resource>:<action>`
# is rejected with MISSING_PERMISSIONS even though the action does exist.
PROPAGATION_TIMEOUT_SECONDS = 30.0
PROPAGATION_POLL_INTERVAL_SECONDS = 0.5


async def retry_while_permissions_propagate(
    operation: Callable[[], Awaitable[TPropagated]],
) -> TPropagated:
    """Run ``operation``, retrying only while the API reports MISSING_PERMISSIONS.

    Bounded polling, not a fixed sleep: the call is retried until it succeeds or
    the deadline passes, so the test is neither slowed down by a worst-case wait
    nor flaky on a slow environment. Every other error propagates immediately --
    a genuinely wrong permission string must still fail the test.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + PROPAGATION_TIMEOUT_SECONDS
    while True:
        try:
            return await operation()
        except PermitApiDetailedError as error:
            if error.code != "MISSING_PERMISSIONS" or loop.time() >= deadline:
                raise
            logger.info(f"permissions on {TEST_RESOURCE_KEY} have not propagated yet, retrying")
            await asyncio.sleep(PROPAGATION_POLL_INTERVAL_SECONDS)


async def list_own_role_keys(permit: Permit) -> List[str]:
    """The keys of roles created by this test, sorted, across all pages.

    The shared environment can easily hold more roles than fit on a single page,
    so paging until a short page comes back is what makes the scoped assertions
    hold no matter how much residue other tests left behind.
    """
    per_page = 100
    page = 1
    keys: List[str] = []
    while True:
        roles = await permit.api.roles.list(page=page, per_page=per_page)
        keys.extend(role.key for role in roles if role.key.startswith(TEST_PREFIX))
        if len(roles) < per_page:
            return sorted(keys)
        page += 1


async def test_roles(permit: Permit):
    logger.info("initial setup of objects")
    # none of this test's roles exist yet
    assert await list_own_role_keys(permit) == []

    try:
        await permit.api.resources.create(
            ResourceCreate(
                key=TEST_RESOURCE_KEY,
                name=TEST_RESOURCE_KEY,
                urn=TEST_RESOURCE_URN,
                actions={
                    "create": ActionBlockEditable(),
                    "read": ActionBlockEditable(),
                    "update": ActionBlockEditable(),
                    "delete": ActionBlockEditable(),
                },
            )
        )

        # create admin role
        admin = await retry_while_permissions_propagate(
            lambda: permit.api.roles.create(
                {
                    "key": TEST_ADMIN_ROLE_KEY,
                    "name": TEST_ADMIN_ROLE_KEY,
                    "description": "a test role",
                    "permissions": [
                        f"{TEST_RESOURCE_KEY}:create",
                        f"{TEST_RESOURCE_KEY}:read",
                    ],
                }
            )
        )

        assert admin is not None
        assert admin.key == TEST_ADMIN_ROLE_KEY
        assert admin.name == TEST_ADMIN_ROLE_KEY
        assert admin.description == "a test role"
        assert admin.permissions is not None
        assert f"{TEST_RESOURCE_KEY}:create" in admin.permissions
        assert f"{TEST_RESOURCE_KEY}:read" in admin.permissions

        # the new role, and only it, shows up in the list
        assert await list_own_role_keys(permit) == [TEST_ADMIN_ROLE_KEY]

        # get non existing role -> 404
        with pytest.raises(PermitApiError) as e:
            await permit.api.roles.get(unique_key("nosuchrole"))
        assert e.value.status_code == 404

        # create existing role -> 409
        with pytest.raises(PermitApiError) as e:
            await permit.api.roles.create(
                {
                    "key": TEST_ADMIN_ROLE_KEY,
                    "name": f"{TEST_ADMIN_ROLE_KEY}-2",
                }
            )
        assert e.value.status_code == 409

        # create empty role
        empty = await permit.api.roles.create(
            {
                "key": TEST_EMPTY_ROLE_KEY,
                "name": TEST_EMPTY_ROLE_KEY,
                "description": "empty role",
            }
        )

        assert empty is not None
        assert empty.key == TEST_EMPTY_ROLE_KEY
        assert empty.name == TEST_EMPTY_ROLE_KEY
        assert empty.description == "empty role"
        assert empty.permissions is not None
        assert len(empty.permissions) == 0

        # both of this test's roles are now listed, and nothing else of its own
        assert await list_own_role_keys(permit) == sorted([TEST_ADMIN_ROLE_KEY, TEST_EMPTY_ROLE_KEY])

        # assign permissions to roles
        assigned_empty = await retry_while_permissions_propagate(
            lambda: permit.api.roles.assign_permissions(TEST_EMPTY_ROLE_KEY, [f"{TEST_RESOURCE_KEY}:delete"])
        )

        assert assigned_empty.key == empty.key
        assert len(assigned_empty.permissions) == 1
        assert f"{TEST_RESOURCE_KEY}:delete" in assigned_empty.permissions

        # remove permissions from role
        await permit.api.roles.remove_permissions(TEST_ADMIN_ROLE_KEY, [f"{TEST_RESOURCE_KEY}:create"])

        # get
        admin = await permit.api.roles.get(TEST_ADMIN_ROLE_KEY)

        # admin changed
        assert admin is not None
        assert admin.key == TEST_ADMIN_ROLE_KEY
        assert admin.description == "a test role"
        assert f"{TEST_RESOURCE_KEY}:create" not in admin.permissions
        assert f"{TEST_RESOURCE_KEY}:read" in admin.permissions

        # update
        await permit.api.roles.update(
            TEST_ADMIN_ROLE_KEY,
            {"description": "wat"},
        )

        # get
        admin = await permit.api.roles.get(TEST_ADMIN_ROLE_KEY)

        # admin changed
        assert admin is not None
        assert admin.key == TEST_ADMIN_ROLE_KEY
        assert admin.description == "wat"
        assert f"{TEST_RESOURCE_KEY}:create" not in admin.permissions
        assert f"{TEST_RESOURCE_KEY}:read" in admin.permissions
    finally:
        for role_key in (TEST_EMPTY_ROLE_KEY, TEST_ADMIN_ROLE_KEY):
            try:
                await permit.api.roles.delete(role_key)
            except PermitApiError as error:
                handle_cleanup_error(error, f"could not delete role {role_key}")
        try:
            await permit.api.resources.delete(TEST_RESOURCE_KEY)
        except PermitApiError as error:
            handle_cleanup_error(error, f"could not delete resource {TEST_RESOURCE_KEY}")
