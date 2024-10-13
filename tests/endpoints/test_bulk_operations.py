import pytest
from loguru import logger

from permit import Permit, RoleCreate, TenantCreate, UserCreate
from permit.api.models import (
    ResourceCreate,
    ResourceInstanceCreate,
    RoleAssignmentCreate,
    RoleAssignmentRemove,
)
from permit.exceptions import PermitApiError, PermitConnectionError
from tests.utils import handle_api_error

# Schema ----------------------------------------------------------------
EDITOR = "editor"
VIEWER = "viewer"

ACCOUNT = ResourceCreate(
    key="Account",
    name="Account",
    urn="prn:gdrive:account",
    description="a google drive account",
    actions={
        "view": {},
        "create": {},
        "delete": {},
        "update": {},
    },
    # tests creation of resource roles as part of the resource
    roles={
        EDITOR: {
            "name": "Admin",
            "permissions": [
                "view",
                "create",
                "delete",
                "update",
            ],
        },
        VIEWER: {
            "name": "Member",
            "permissions": [
                "view",
            ],
        },
    },
)


USER_A = UserCreate(
    **dict(
        key="auth0|asaf",
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
USER_C = UserCreate(
    key="auth0|jane",
    email="jane@permit.io",
    first_name="Jane",
    last_name="Doe",
    attributes={"age": 25},
)

TENANT_1 = TenantCreate(key="ten1", name="Tenant 1")
TENANT_2 = TenantCreate(key="ten2", name="Tenant 2")

ADMIN = RoleCreate(
    key="admin",
    name="Admin",
    permissions=[
        f"{ACCOUNT.key}:view",
        f"{ACCOUNT.key}:create",
        f"{ACCOUNT.key}:delete",
        f"{ACCOUNT.key}:update",
    ],
)
MEMBER = RoleCreate(key="member", name="Member")

CREATED_USERS = [USER_A, USER_B, USER_C]
CREATED_TENANTS = [TENANT_1, TENANT_2]

ACC1 = ResourceInstanceCreate(
    resource=ACCOUNT.key,
    key="acc1",
    tenant=TENANT_1.key,
)

ACC2 = ResourceInstanceCreate(
    resource=ACCOUNT.key,
    key="acc2",
    tenant=TENANT_1.key,
)

ACC3 = ResourceInstanceCreate(
    resource=ACCOUNT.key,
    key="acc3",
    tenant=TENANT_2.key,
)

CREATED_RESOURCE_INSTANCES = [ACC1, ACC2, ACC3]

CREATED_ASSIGNMENTS = [
    # admin on tenant
    RoleAssignmentCreate(
        user=USER_A.key,
        role=ADMIN.key,
        tenant=TENANT_1.key,
    ),
    # resource instance roles
    RoleAssignmentCreate(
        user=USER_A.key,
        role=EDITOR,
        tenant=TENANT_1.key,
        resource_instance=f"{ACC1.resource}:{ACC1.key}",
    ),
    RoleAssignmentCreate(
        user=USER_B.key,
        role=VIEWER,
        tenant=TENANT_1.key,
        resource_instance=f"{ACC2.resource}:{ACC2.key}",
    ),
    # this instance will be created implicitly
    RoleAssignmentCreate(
        user=USER_C.key,
        role=VIEWER,
        tenant=TENANT_2.key,
        resource_instance=f"{ACC3.resource}:{ACC3.key}",
    ),
]


async def test_bulk_operations(permit: Permit):
    try:
        ## create resource  and global role ------------------------------------
        resource = await permit.api.resources.create(ACCOUNT)
        assert resource is not None
        assert resource.key == ACCOUNT.key

        role = await permit.api.roles.create(ADMIN)
        assert role is not None
        assert role.key == ADMIN.key

        ## bulk create tenants ------------------------------------

        # initial number of tenants
        tenants = await permit.api.tenants.list()
        len_tenants_original = len(tenants)

        # create tenants in bulk
        await permit.api.tenants.bulk_create(CREATED_TENANTS)

        # check increased number of tenants
        tenants = await permit.api.tenants.list()
        assert len(tenants) == len_tenants_original + len(CREATED_TENANTS)

        ## bulk create users ------------------------------------

        # initial number of users
        users = (await permit.api.users.list()).data
        len_users_original = len(users)

        # create users in bulk
        await permit.api.users.bulk_create(CREATED_USERS)

        # check increased number of users
        users = (await permit.api.users.list()).data
        assert len(users) == len_users_original + len(CREATED_USERS)

        ## bulk create resource instances ------------------------------------
        # initial number of users
        instances = await permit.api.resource_instances.list()
        len_instances_original = len(instances)

        # create instances in bulk (keep one to create implicitly by role assignment)
        await permit.api.resource_instances.bulk_replace(CREATED_RESOURCE_INSTANCES[:-1])

        # check increased number of instances
        instances = await permit.api.resource_instances.list()
        assert len(instances) == len_instances_original + len(CREATED_RESOURCE_INSTANCES) - 1

        ## bulk create role assignments ------------------------------------

        # initial number of role assignments
        assignments = await permit.api.role_assignments.list()
        len_assignments_original = len(assignments)

        # create role assignments in bulk
        await permit.api.role_assignments.bulk_assign(CREATED_ASSIGNMENTS)

        # check increased number of role assignments
        assignments = await permit.api.role_assignments.list()
        assert len(assignments) == len_assignments_original + len(CREATED_ASSIGNMENTS)

        # check that instance created implicitly
        instances = await permit.api.resource_instances.list()
        assert len(instances) == len_instances_original + len(CREATED_RESOURCE_INSTANCES)

        ## bulk delete resource instances -----------------------------------
        await permit.api.resource_instances.bulk_delete(
            [f"{inst.resource}:{inst.key}" for inst in CREATED_RESOURCE_INSTANCES]
        )

        instances = await permit.api.resource_instances.list()
        assert len(instances) == len_instances_original

        assignments = await permit.api.role_assignments.list()
        assert len(assignments) == len_assignments_original + 1  # (tenant role)

        ## bulk delete users -----------------------------------
        await permit.api.users.bulk_delete([user.key for user in CREATED_USERS])

        users = (await permit.api.users.list()).data
        assert len(users) == len_users_original

        assignments = await permit.api.role_assignments.list()
        assert len(assignments) == len_assignments_original

        ## bulk delete tenants -----------------------------------
        await permit.api.tenants.bulk_delete([tenant.key for tenant in CREATED_TENANTS])

        tenants = await permit.api.tenants.list()
        assert len(tenants) == len_tenants_original

    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError as error:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
