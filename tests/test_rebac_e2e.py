from dataclasses import dataclass

import pytest
from loguru import logger

from permit import Permit
from permit.api.models import (
    DerivedRoleBlockEdit,
    DerivedRoleRuleCreate,
    RelationCreate,
    ResourceCreate,
    ResourceRoleCreate,
    RoleAssignmentCreate,
    TenantCreate,
    UserCreate,
)
from permit.exceptions import PermitApiError
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

TENANT_1 = TenantCreate(key="ten1", name="Tenant 1")
TENANT_2 = TenantCreate(key="ten2", name="Tenant 2")

ACCOUNT = ResourceCreate(
    key="Account",
    name="Account",
    urn="prn:gdrive:account",
    description="a google drive account",
    actions={
        "create": {},
        "invite-user": {},
        "delete": {},
        "view-members": {},
        "create-folder": {},
        "create-document": {},
    },
    # tests creation of resource roles as part of the resource
    roles={
        "admin": {
            "name": "Admin",
            "permissions": [
                "create",
                "invite-user",
                "delete",
                "view-members",
                "create-folder",
                "create-document",
            ],
        },
        "member": {
            "name": "Member",
            "permissions": [
                "view-members",
                "create-folder",
                "create-document",
            ],
        },
    },
)

FOLDER = ResourceCreate(
    key="Folder",
    name="Folder",
    urn="prn:gdrive:folder",
    description="a folder",
    actions={
        "read": {},
        "rename": {},
        "delete": {},
        "create-document": {},
    },
    # tests creation of resource relations as part of the resource
    relations={
        "account": f"{ACCOUNT.key}",
    },
)

DOCUMENT = ResourceCreate(
    key="Document",
    name="Document",
    urn="prn:gdrive:document",
    description="a document",
    actions={
        "read": {},
        "update": {},
        "delete": {},
        "comment": {},
    },
)

CREATED_USERS = [USER_A, USER_B]
CREATED_TENANTS = [TENANT_1, TENANT_2]
CREATED_RESOURCES = [ACCOUNT, FOLDER, DOCUMENT]

RESOURCE_ROLES = {
    FOLDER.key: [
        ResourceRoleCreate(key="viewer", name="Viewer", permissions=[f"read"]),
        ResourceRoleCreate(
            key="commenter",
            name="Commenter",
            permissions=[f"read"],
        ),
        ResourceRoleCreate(
            key="editor",
            name="Editor",
            permissions=[
                f"read",
                f"rename",
                f"delete",
                f"create-document",
            ],
            # tests creation of role derivation as part of the resource role
            # (account admin is editor on everything)
            granted_to=DerivedRoleBlockEdit(
                users_with_role=[
                    DerivedRoleRuleCreate(
                        role="admin",
                        on_resource="Account",
                        linked_by_relation="account",
                    )
                ]
            ),
        ),
    ],
    DOCUMENT.key: [
        ResourceRoleCreate(key="viewer", name="Viewer", permissions=[f"read"]),
        ResourceRoleCreate(
            key="commenter",
            name="Commenter",
            permissions=[f"read", f"comment"],
        ),
        ResourceRoleCreate(
            key="editor",
            name="Editor",
            permissions=[
                f"read",
                f"comment",
                f"update",
                f"delete",
            ],
        ),
    ],
}

RESOURCE_RELATIONS = {
    DOCUMENT.key: [
        RelationCreate(
            key="parent",
            name="Parent Folder",
            subject_resource=f"{FOLDER.key}",
        ),
    ],
}


@dataclass
class ShortDerivation:
    source_role: str
    derived_role: str
    via_relation: str

    @property
    def source_role_key(self) -> str:
        return self.source_role.split("#")[1]

    @property
    def source_resource_key(self) -> str:
        return self.source_role.split("#")[0]

    @property
    def derived_role_key(self) -> str:
        return self.derived_role.split("#")[1]

    @property
    def object_key(self) -> str:
        return self.derived_role.split("#")[0]


ROLE_DERIVATIONS = [
    *[
        # role on folder => same role on document inside the folder
        ShortDerivation(
            source_role=f"{FOLDER.key}#{role}",
            derived_role=f"{DOCUMENT.key}#{role}",
            via_relation="parent",
        )
        for role in [
            "viewer",
            "commenter",
            "editor",
        ]
    ],
]


async def cleanup(permit: Permit):
    print("Running cleanup...")
    try:
        for user in CREATED_USERS:
            try:
                await permit.api.users.delete(user.key)
            except PermitApiError as error:
                if error.status_code == 404:
                    print(f"SKIPPING delete, user does not exists: {user.key}")
        for tenant in CREATED_TENANTS:
            try:
                await permit.api.tenants.delete(tenant.key)
            except PermitApiError as error:
                if error.status_code == 404:
                    print(f"SKIPPING delete, tenant does not exists: {tenant.key}")
        for resource in CREATED_RESOURCES:
            try:
                await permit.api.resources.delete(resource.key)
            except PermitApiError as error:
                if error.status_code == 404:
                    print(f"SKIPPING delete, resource does not exists: {resource.key}")
    except PermitApiError as error:
        handle_api_error(error, "Got API Error during cleanup")
    except Exception as error:
        logger.error(f"Got error during cleanup: {error}")
        pytest.fail(f"Got error during cleanup: {error}")
    print("Cleanup finished.")


async def test_users_tenants(permit: Permit):
    logger.info("initial setup of objects")
    await cleanup(permit)
    try:
        # create tenants
        for tenant_data in CREATED_TENANTS:
            print(f"creating tenant: {tenant_data.key}")
            tenant = await permit.api.tenants.create(tenant_data)
            assert tenant is not None
            assert tenant.key == tenant_data.key
            assert tenant.name == tenant_data.name
            assert tenant.description is None

        # create users
        for user_data in CREATED_USERS:
            print(f"creating user: {user_data.key}")
            user = await permit.api.users.create(user_data)
            assert user is not None
            assert user.key == user_data.key
            assert user.email == user_data.email
            assert user.first_name == user_data.first_name
            assert user.last_name == user_data.last_name
            assert set(user.attributes.keys()) == set(user_data.attributes.keys())

        # create resources
        for resource_data in CREATED_RESOURCES:
            print(f"creating resource: {resource_data.key}")
            resource = await permit.api.resources.create(resource_data)
            assert resource is not None
            assert resource.key == resource_data.key
            assert resource.name == resource_data.name
            assert resource.description == resource_data.description
            assert resource.urn == resource_data.urn
            assert resource.actions is not None
            assert len(resource.actions) == len(resource_data.actions)
            assert set(resource.actions.keys()) == set(resource_data.actions.keys())

        # create resource roles
        for resource_key, resource_roles in iter(RESOURCE_ROLES.items()):
            for role_data in resource_roles:
                print(f"creating resource role: {resource_key}#{role_data.key}")
                role = await permit.api.resource_roles.create(
                    resource_key=resource_key, role_data=role_data
                )
                assert role is not None
                assert role.key == role_data.key
                assert role.name == role_data.name
                assert role.description == role_data.description
                assert role.permissions is not None
                assert len(role.permissions) == len(role_data.permissions)

        # create resource relations
        for resource_key, resource_relations in iter(RESOURCE_RELATIONS.items()):
            for relation_data in resource_relations:
                print(
                    f"creating resource relation: {resource_key}->{relation_data.key}"
                )
                relation = await permit.api.resource_relations.create(
                    resource_key=resource_key, relation_data=relation_data
                )
                assert relation is not None
                assert relation.key == relation_data.key
                assert relation.name == relation_data.name
                assert relation.subject_resource == relation_data.subject_resource
                assert relation.object_resource == resource_key

        # create role derivations
        for derivation_data in ROLE_DERIVATIONS:
            print(
                f"creating derivation: {derivation_data.source_role} -> {derivation_data.derived_role} (via {derivation_data.via_relation})"
            )
            derivation = await permit.api.resource_roles.create_role_derivation(
                resource_key=derivation_data.object_key,
                role_key=derivation_data.derived_role_key,
                derivation_rule=DerivedRoleRuleCreate(
                    role=derivation_data.source_role_key,
                    on_resource=derivation_data.source_resource_key,
                    linked_by_relation=derivation_data.via_relation,
                ),
            )
            assert derivation is not None
            assert derivation.role == derivation_data.source_role_key
            assert derivation.on_resource == derivation_data.source_resource_key
            assert derivation.linked_by_relation == derivation_data.via_relation

        # bulk role assignments
        # await permit.api.role_assignments.bulk_assign(
        #     [
        #         RoleAssignmentCreate(
        #             user=USER_A.key, role=ADMIN.key, tenant=TENANT_1.key
        #         ),
        #         RoleAssignmentCreate(
        #             user=USER_B.key, role=VIEWER.key, tenant=TENANT_1.key
        #         ),
        #     ]
        # )

        # # get tenant users
        # users1 = await permit.api.tenants.list_tenant_users(TENANT_1.key)
        # assert len(users1.data) == 2
        # users2 = await permit.api.tenants.list_tenant_users(TENANT_2.key)
        # assert len(users2.data) == 0

        # # get assigned roles of user A
        # roles_a1 = await permit.api.users.get_assigned_roles(
        #     USER_A.key, tenant=TENANT_1.key
        # )
        # assert len(roles_a1) == 1
        # assert roles_a1[0].user == USER_A.key
        # assert roles_a1[0].role == ADMIN.key
        # assert roles_a1[0].tenant == TENANT_1.key
        # roles_a2 = await permit.api.users.get_assigned_roles(
        #     USER_A.key, tenant=TENANT_2.key
        # )
        # assert len(roles_a2) == 0

        # # assign role
        # ra = await permit.api.users.assign_role(
        #     RoleAssignmentCreate(user=USER_C.key, role=ADMIN.key, tenant=TENANT_2.key)
        # )
        # assert ra.user == USER_C.key or ra.user == USER_C.email  # TODO: fix bug in api
        # assert ra.role == ADMIN.key
        # assert ra.tenant == TENANT_2.key

        # # add user a to another tenant
        # ra = await permit.api.users.assign_role(
        #     RoleAssignmentCreate(user=USER_A.key, role=ADMIN.key, tenant=TENANT_2.key)
        # )

        # # get assigned roles
        # roles_a = await permit.api.users.get_assigned_roles(USER_A.key)
        # assert len(roles_a) == 2
        # assert len(set([ra.tenant for ra in roles_a])) == 2  # user in 2 tenants

        # # delete tenant user
        # tenant2_users = await permit.api.tenants.list_tenant_users(TENANT_2.key)
        # assert len(tenant2_users.data) == 2
        # await permit.api.tenants.delete_tenant_user(TENANT_2.key, USER_A.key)
        # tenant2_users = await permit.api.tenants.list_tenant_users(TENANT_2.key)
        # assert (
        #     len(tenant2_users.data) == 2
        # )  # TODO: change to 1, fix bug in delete_tenant_user

        # # list role assignments
        # ras = await permit.api.role_assignments.list()
        # assert len(ras) == 3

        # # role unassign
        # await permit.api.role_assignments.unassign(
        #     RoleAssignmentRemove(user=USER_C.key, role=ADMIN.key, tenant=TENANT_2.key)
        # )

        # # list role assignments
        # ras = await permit.api.role_assignments.list()
        # assert len(ras) == 2

        # # bulk unassign
        # await permit.api.role_assignments.bulk_unassign(
        #     [
        #         RoleAssignmentRemove(
        #             user=USER_A.key, role=ADMIN.key, tenant=TENANT_1.key
        #         ),
        #         RoleAssignmentRemove(
        #             user=USER_B.key, role=VIEWER.key, tenant=TENANT_1.key
        #         ),
        #     ]
        # )

        # # list role assignments
        # ras = await permit.api.role_assignments.list()
        # assert len(ras) == 0
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        await cleanup(permit)
