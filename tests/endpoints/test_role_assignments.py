from contextlib import contextmanager

from permit import Permit, PermitApiError, RoleAssignmentCreate, RoleCreate, UserCreate


@contextmanager
def suppress_409():
    try:
        yield
    except PermitApiError as e:
        if e.status_code != 409:
            raise e


async def create_role_assignments(permit: Permit, role_key: str, user_count: int = 10):
    with suppress_409():
        await permit.api.roles.create(RoleCreate(key=role_key, name=role_key))
    with suppress_409():
        await permit.api.users.bulk_create(
            [UserCreate(key=f"user-{index}") for index in range(user_count)]
        )
    with suppress_409():
        await permit.api.role_assignments.bulk_assign(
            [
                RoleAssignmentCreate(
                    role=role_key, user=f"user-{index}", tenant="default"
                )
                for index in range(user_count)
            ]
        )


async def test_list_filter_by_role(permit: Permit):
    await create_role_assignments(permit, "role-1")
    await create_role_assignments(permit, "role-2")
    role_assignments = await permit.api.role_assignments.list(role_key="role-1")
    assert len(role_assignments) == 10
    assert {ra.role for ra in role_assignments} == {"role-1"}


async def test_list_filter_by_role_multiple(permit: Permit):
    await create_role_assignments(permit, "role-1")
    await create_role_assignments(permit, "role-2")
    await create_role_assignments(permit, "role-3")
    role_assignments = await permit.api.role_assignments.list(
        role_key=["role-1", "role-2"]
    )
    assert len(role_assignments) == 20
    assert {ra.role for ra in role_assignments} == {"role-1", "role-2"}
