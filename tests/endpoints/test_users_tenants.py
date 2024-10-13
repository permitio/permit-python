import pytest
from loguru import logger

from permit import Permit, RoleCreate, TenantCreate, UserCreate
from permit.api.models import RoleAssignmentCreate, RoleAssignmentRemove
from permit.exceptions import PermitApiError, PermitConnectionError
from tests.utils import handle_api_error

USER_A = UserCreate(
    **dict(
        key="asaf@permit.io",
        email="asaf@permit.io",
        first_name="Asaf",
        last_name="Cohen",
        attributes={"age": 35},
    )
)
USER_B = UserCreate(
    **dict(
        key="auth0|john",
        email="john@permit.io",
        first_name="John",
        last_name="Doe",
        attributes={"age": 27},
    )
)
USER_BB = UserCreate(
    **dict(
        key="auth0|john",
        email="john@apple.com",
        first_name="John",
        last_name="Appleseed",
        attributes={"age": 27},
    )
)
USER_C = UserCreate(
    key="auth0|jane",
    email="jane@permit.io",
    first_name="Jane",
    last_name="Doe",
    attributes={"age": 25},
)

TENANT_1 = TenantCreate(key="ten1", name="Tenant 1")
TENANT_2 = TenantCreate(key="ten2", name="Tenant 2")

ADMIN = RoleCreate(key="admin", name="Admin")
VIEWER = RoleCreate(key="viewer", name="Viewer")

CREATED_USERS = [USER_A, USER_B, USER_C]
CREATED_TENANTS = [TENANT_1, TENANT_2]
CREATED_ROLES = [ADMIN, VIEWER]


async def test_users_tenants(permit: Permit):
    logger.info("initial setup of objects")
    len_original = 0
    try:
        # initial number of tenants
        tenants = await permit.api.tenants.list()
        len_original = len(tenants)

        # create tenants
        for tenant_data in CREATED_TENANTS:
            tenant = await permit.api.tenants.create(tenant_data)
            assert tenant is not None
            assert tenant.key == tenant_data.key
            assert tenant.name == tenant_data.name
            assert tenant.description is None

        # increased number of tenants by 1
        tenants = await permit.api.tenants.list()
        assert len(tenants) == len_original + len(CREATED_TENANTS)

        # get non existing tenant -> 404
        with pytest.raises(PermitApiError) as e:
            await permit.api.tenants.get("nosuchtenant")
        assert e.value.status_code == 404

        # create existing tenant -> 409
        with pytest.raises(PermitApiError) as e:
            await permit.api.tenants.create(TENANT_1)
        assert e.value.status_code == 409

        # get tenant
        t1 = await permit.api.tenants.get(TENANT_1.key)
        assert t1.key == TENANT_1.key

        # create users
        for user_data in CREATED_USERS:
            user = await permit.api.users.create(user_data)
            assert user is not None
            assert user.key == user_data.key
            assert user.email == user_data.email
            assert user.first_name == user_data.first_name
            assert user.last_name == user_data.last_name
            assert set(user.attributes.keys()) == set(user_data.attributes.keys())

        # get non existing user -> 404
        with pytest.raises(PermitApiError) as e:
            await permit.api.users.get("nosuchuser")
        assert e.value.status_code == 404

        # create existing user -> 409
        with pytest.raises(PermitApiError) as e:
            await permit.api.users.create(USER_BB)
        assert e.value.status_code == 409

        # get user
        ub = await permit.api.users.get(USER_B.key)
        assert ub.key == USER_B.key
        assert ub.email == USER_B.email

        # but we can sync the user
        user = await permit.api.users.sync(USER_BB)
        assert user is not None
        assert user.key == USER_BB.key
        assert user.email == USER_BB.email
        assert user.first_name == USER_BB.first_name
        assert user.last_name == USER_BB.last_name
        assert set(user.attributes.keys()) == set(USER_BB.attributes.keys())

        # get user after sync/update
        ub = await permit.api.users.get(USER_B.key)
        assert ub.key == USER_B.key
        assert ub.email != USER_B.email
        assert ub.email == USER_BB.email

        # update tenant
        t2 = await permit.api.tenants.update(TENANT_2.key, {"description": "t2 update"})
        assert t2.key == TENANT_2.key
        assert t2.description != TENANT_2.description
        assert t2.description == "t2 update"

        # get tenant users
        users = await permit.api.tenants.list_tenant_users(TENANT_1.key)
        assert len(users.data) == 0

        # create roles
        for role_data in CREATED_ROLES:
            await permit.api.roles.create(role_data)

        # bulk role assignment to tenant 1
        await permit.api.role_assignments.bulk_assign(
            [
                RoleAssignmentCreate(user=USER_A.key, role=ADMIN.key, tenant=TENANT_1.key),
                RoleAssignmentCreate(user=USER_B.key, role=VIEWER.key, tenant=TENANT_1.key),
            ]
        )

        # get tenant users
        users1 = await permit.api.tenants.list_tenant_users(TENANT_1.key)
        assert len(users1.data) == 2
        users2 = await permit.api.tenants.list_tenant_users(TENANT_2.key)
        assert len(users2.data) == 0

        # get assigned roles of user A
        roles_a1 = await permit.api.users.get_assigned_roles(USER_A.key, tenant=TENANT_1.key)
        assert len(roles_a1) == 1
        assert roles_a1[0].user == USER_A.key
        assert roles_a1[0].role == ADMIN.key
        assert roles_a1[0].tenant == TENANT_1.key
        roles_a2 = await permit.api.users.get_assigned_roles(USER_A.key, tenant=TENANT_2.key)
        assert len(roles_a2) == 0

        # assign role
        ra = await permit.api.users.assign_role(
            RoleAssignmentCreate(user=USER_C.key, role=ADMIN.key, tenant=TENANT_2.key)
        )
        assert ra.user == USER_C.key or ra.user == USER_C.email  # TODO: fix bug in api
        assert ra.role == ADMIN.key
        assert ra.tenant == TENANT_2.key

        # add user a to another tenant
        ra = await permit.api.users.assign_role(
            RoleAssignmentCreate(user=USER_A.key, role=ADMIN.key, tenant=TENANT_2.key)
        )

        # get assigned roles
        roles_a = await permit.api.users.get_assigned_roles(USER_A.key)
        assert len(roles_a) == 2
        assert len(set([ra.tenant for ra in roles_a])) == 2  # user in 2 tenants

        # delete tenant user
        tenant2_users = await permit.api.tenants.list_tenant_users(TENANT_2.key)
        assert len(tenant2_users.data) == 2
        await permit.api.tenants.delete_tenant_user(TENANT_2.key, USER_A.key)
        tenant2_users = await permit.api.tenants.list_tenant_users(TENANT_2.key)
        assert len(tenant2_users.data) == 2  # TODO: change to 1, fix bug in delete_tenant_user

        # list role assignments
        ras = await permit.api.role_assignments.list()
        assert len(ras) == 3

        # role unassign
        await permit.api.role_assignments.unassign(
            RoleAssignmentRemove(user=USER_C.key, role=ADMIN.key, tenant=TENANT_2.key)
        )

        # list role assignments
        ras = await permit.api.role_assignments.list()
        assert len(ras) == 2

        # bulk unassign
        await permit.api.role_assignments.bulk_unassign(
            [
                RoleAssignmentRemove(user=USER_A.key, role=ADMIN.key, tenant=TENANT_1.key),
                RoleAssignmentRemove(user=USER_B.key, role=VIEWER.key, tenant=TENANT_1.key),
            ]
        )

        # list role assignments
        ras = await permit.api.role_assignments.list()
        assert len(ras) == 0
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError as error:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        # cleanup
        try:
            for role in CREATED_ROLES:
                await permit.api.roles.delete(role.key)
            for user in CREATED_USERS:
                await permit.api.users.delete(user.key)
            for tenant in CREATED_TENANTS:
                await permit.api.tenants.delete(tenant.key)
            assert len(await permit.api.tenants.list()) == len_original
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError as error:
            raise
        except Exception as error:
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")
