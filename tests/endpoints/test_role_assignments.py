import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from loguru import logger

from permit import (
    Permit,
    PermitApiError,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleCreate,
    UserCreate,
)
from permit.exceptions import PermitApiDetailedError
from tests.utils import handle_cleanup_error, unique_key

TPropagated = TypeVar("TPropagated")

USER_COUNT = 10
# A user that was just created is not always visible to the role-assignment
# endpoint immediately, and a fresh assignment is not always listed at once.
# Both are bounded polls, never a fixed sleep.
PROPAGATION_TIMEOUT_SECONDS = 30.0
PROPAGATION_POLL_INTERVAL_SECONDS = 0.5


def user_keys(prefix: str, count: int = USER_COUNT) -> list[str]:
    return [f"{prefix}-user-{index}" for index in range(count)]


async def retry_while_not_found(
    operation: Callable[[], Awaitable[TPropagated]],
) -> TPropagated:
    """Run ``operation``, retrying only while the API reports NOT_FOUND.

    ``users.bulk_create`` returns before every user is readable by the
    role-assignment endpoint, which answers 404 for the user in the meantime.
    Every other error propagates immediately, so a genuinely missing object
    still fails the test once the deadline passes.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + PROPAGATION_TIMEOUT_SECONDS
    while True:
        try:
            return await operation()
        except PermitApiDetailedError as error:
            if error.code != "NOT_FOUND" or loop.time() >= deadline:
                raise
            logger.info("referenced object has not propagated yet, retrying")
            await asyncio.sleep(PROPAGATION_POLL_INTERVAL_SECONDS)


async def create_role_assignments(permit: Permit, role_key: str, users: Sequence[str]) -> None:
    """Create a role, its users and the assignments binding them, in the default tenant.

    Every key handed in is unique to the calling test, so a 409 here is a real
    defect rather than residue from another test and is deliberately not
    suppressed. Swallowing it used to hide the interesting failure: the bulk
    user create is all-or-nothing, so a single pre-existing key made it create
    *no* users at all and the assignment that followed failed with a confusing
    404 on the first user.
    """
    await permit.api.roles.create(RoleCreate(key=role_key, name=role_key))
    await permit.api.users.bulk_create([UserCreate(key=user) for user in users])
    await retry_while_not_found(
        lambda: permit.api.role_assignments.bulk_assign(
            [RoleAssignmentCreate(role=role_key, user=user, tenant="default") for user in users]
        )
    )


async def list_assignments(
    permit: Permit,
    role_key: str | list[str],
    expected_count: int,
) -> list[RoleAssignmentRead]:
    """List the assignments of the given role(s), polling until they are all visible.

    Returns whatever the last call reported once the count matches or the
    deadline passes, so the caller's assertions -- not this helper -- decide
    whether the result is correct.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + PROPAGATION_TIMEOUT_SECONDS
    while True:
        assignments = await permit.api.role_assignments.list(role_key=role_key)
        if len(assignments) >= expected_count or loop.time() >= deadline:
            return assignments
        await asyncio.sleep(PROPAGATION_POLL_INTERVAL_SECONDS)


async def cleanup(permit: Permit, role_keys: Sequence[str], users: Sequence[str]) -> None:
    """Remove everything a test created. Deleting a role or a user also drops its assignments."""
    for role_key in role_keys:
        try:
            await permit.api.roles.delete(role_key)
        except PermitApiError as error:
            handle_cleanup_error(error, f"could not delete role {role_key}")
    for user in users:
        try:
            await permit.api.users.delete(user)
        except PermitApiError as error:
            handle_cleanup_error(error, f"could not delete user {user}")


async def test_list_filter_by_role(permit: Permit) -> None:
    prefix = unique_key("ra-single")
    role_1 = f"{prefix}-role-1"
    role_2 = f"{prefix}-role-2"
    users_1 = user_keys(f"{prefix}-r1")
    users_2 = user_keys(f"{prefix}-r2")

    try:
        await create_role_assignments(permit, role_1, users_1)
        await create_role_assignments(permit, role_2, users_2)

        role_assignments = await list_assignments(permit, role_1, expected_count=len(users_1))

        # the filter returns this role's assignments, all of them and nothing else --
        # not the ones created for role_2 alongside them, nor any residue in the
        # shared environment
        assert {ra.role for ra in role_assignments} == {role_1}
        assert {ra.user for ra in role_assignments} == set(users_1)
        assert len(role_assignments) == len(users_1)
    finally:
        await cleanup(permit, [role_1, role_2], [*users_1, *users_2])


async def test_list_filter_by_role_multiple(permit: Permit) -> None:
    prefix = unique_key("ra-multi")
    role_1 = f"{prefix}-role-1"
    role_2 = f"{prefix}-role-2"
    role_3 = f"{prefix}-role-3"
    users_1 = user_keys(f"{prefix}-r1")
    users_2 = user_keys(f"{prefix}-r2")
    users_3 = user_keys(f"{prefix}-r3")

    try:
        await create_role_assignments(permit, role_1, users_1)
        await create_role_assignments(permit, role_2, users_2)
        await create_role_assignments(permit, role_3, users_3)

        role_assignments = await list_assignments(
            permit, [role_1, role_2], expected_count=len(users_1) + len(users_2)
        )

        # a multi-valued role filter is a union of the roles asked for, and
        # excludes role_3 which was created in the same environment
        assert {ra.role for ra in role_assignments} == {role_1, role_2}
        assert {ra.user for ra in role_assignments} == set(users_1) | set(users_2)
        assert len(role_assignments) == len(users_1) + len(users_2)
    finally:
        await cleanup(permit, [role_1, role_2, role_3], [*users_1, *users_2, *users_3])
