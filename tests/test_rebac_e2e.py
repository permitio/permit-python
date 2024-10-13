import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Optional

import pytest
from loguru import logger

from permit import Permit
from permit.api.models import (
    DerivedRoleBlockEdit,
    DerivedRoleRuleCreate,
    PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings,
    RelationCreate,
    RelationshipTupleCreate,
    RelationshipTupleDelete,
    ResourceCreate,
    ResourceInstanceCreate,
    ResourceRoleCreate,
    RoleAssignmentCreate,
    RoleAssignmentRemove,
    TenantCreate,
    UserCreate,
)
from permit.exceptions import PermitApiError
from tests.utils import handle_api_error


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


@dataclass
class CheckAssertion:
    user: str
    action: str
    resource: dict
    expected_decision: bool
    pre_assertion_hook: Optional[Callable[[Permit], Awaitable[Any]]] = None
    post_assertion_hook: Optional[Callable[[Permit], Awaitable[Any]]] = None


@dataclass
class PermissionAssertions:
    assignments: List[RoleAssignmentCreate]
    assertions: List[CheckAssertion]


# Graph Schema ----------------------------------------------------------------
# role keys
VIEWER = "viewer"
COMMENTER = "commenter"
EDITOR = "editor"
ADMIN = "admin"
MEMBER = "member"
WATCHER = "watcher"

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
        ADMIN: {
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
        MEMBER: {
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

RESOURCE_ROLES = {
    FOLDER.key: [
        ResourceRoleCreate(
            key=VIEWER,
            name="Viewer",
            permissions=["read"],
        ),
        ResourceRoleCreate(
            key=COMMENTER,
            name="Commenter",
            permissions=["read", "rename"],
            granted_to=DerivedRoleBlockEdit(
                users_with_role=[
                    DerivedRoleRuleCreate(
                        role=MEMBER,
                        on_resource="Account",
                        linked_by_relation="account",
                        when=PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings(
                            no_direct_roles_on_object=True,
                        ),
                    )
                ]
            ),
        ),
        ResourceRoleCreate(
            key=EDITOR,
            name="Editor",
            permissions=[
                "read",
                "rename",
                "delete",
                "create-document",
            ],
            # tests creation of role derivation as part of the resource role
            # (account admin is editor on everything)
            granted_to=DerivedRoleBlockEdit(
                when=PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings(
                    no_direct_roles_on_object=True,
                ),
                users_with_role=[
                    DerivedRoleRuleCreate(
                        role=ADMIN,
                        on_resource="Account",
                        linked_by_relation="account",
                    )
                ],
            ),
        ),
    ],
    DOCUMENT.key: [
        ResourceRoleCreate(key=VIEWER, name="Viewer", permissions=["read"]),
        ResourceRoleCreate(
            key=COMMENTER,
            name="Commenter",
            permissions=["read", "comment"],
        ),
        ResourceRoleCreate(
            key=EDITOR,
            name="Editor",
            permissions=[
                "read",
                "comment",
                "update",
                "delete",
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

CREATED_RESOURCES = [ACCOUNT, FOLDER, DOCUMENT]

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

# Data ------------------------------------------------------------------------
USER_PERMIT = UserCreate(
    key="asaf@permit.io",
    email="asaf@permit.io",
    first_name="Asaf",
    last_name="Cohen",
    attributes={"age": 35},
)
USER_CC = UserCreate(
    key="auth0|john",
    email="john@cocacola.com",
    first_name="John",
    last_name="Doe",
    attributes={"age": 27},
)

CREATED_USERS = [USER_PERMIT, USER_CC]

TENANT_PERMIT = TenantCreate(key="permit", name="Permit.io")
TENANT_CC = TenantCreate(key="cocacola", name="Coca Cola")

CREATED_TENANTS = [TENANT_PERMIT, TENANT_CC]

# Document -> parent -> Folder -> account -> Account
RELATIONSHIPS = [
    # finance folder contains 2 documents
    (f"{FOLDER.key}:finance", "parent", f"{DOCUMENT.key}:budget23", TENANT_PERMIT.key),
    (
        f"{FOLDER.key}:finance",
        "parent",
        f"{DOCUMENT.key}:june-expenses",
        TENANT_PERMIT.key,
    ),
    # rnd folder contains 2 documents
    (f"{FOLDER.key}:rnd", "parent", f"{DOCUMENT.key}:architecture", TENANT_PERMIT.key),
    (f"{FOLDER.key}:rnd", "parent", f"{DOCUMENT.key}:opal", TENANT_PERMIT.key),
    # folders belongs in permit g-drive account
    (f"{ACCOUNT.key}:permitio", "account", f"{FOLDER.key}:finance", TENANT_PERMIT.key),
    (f"{ACCOUNT.key}:permitio", "account", f"{FOLDER.key}:rnd", TENANT_PERMIT.key),
    # another account->folder->doc belongs to another tenant
    (f"{FOLDER.key}:recipes", "parent", f"{DOCUMENT.key}:secret-recipe", TENANT_CC.key),
    (f"{ACCOUNT.key}:cocacola", "account", f"{FOLDER.key}:recipes", TENANT_CC.key),
]

BULK_RELATIONSHIPS = [
    # rnd folder contains 2 documents
    (f"{FOLDER.key}:media", "parent", f"{DOCUMENT.key}:movie1", TENANT_PERMIT.key),
    (f"{FOLDER.key}:media", "parent", f"{DOCUMENT.key}:movie2", TENANT_PERMIT.key),
]

BULK_RELATIONSHIPS_INSTANCES = [
    f"{FOLDER.key}:media",
    f"{DOCUMENT.key}:movie1",
    f"{DOCUMENT.key}:movie2",
]

ASSIGNMENTS_AND_ASSERTIONS: List[PermissionAssertions] = [
    # direct access
    PermissionAssertions(
        assignments=[
            RoleAssignmentCreate(
                user=USER_PERMIT.key,
                role=VIEWER,
                resource_instance=f"{DOCUMENT.key}:architecture",
                tenant=TENANT_PERMIT.key,
            )
        ],
        assertions=[
            # direct access allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="read",
                resource={
                    "type": DOCUMENT.key,
                    "key": "architecture",
                    "tenant": TENANT_PERMIT.key,
                },
                expected_decision=True,
            ),
            # higher permissions not allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="comment",
                resource={
                    "type": DOCUMENT.key,
                    "key": "architecture",
                    "tenant": TENANT_PERMIT.key,
                },
                expected_decision=False,
            ),
            # other instances not allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="comment",
                resource={"type": DOCUMENT.key, "key": "opal", "tenant": TENANT_PERMIT.key},
                expected_decision=False,
            ),
        ],
    ),
    # access from higher level
    PermissionAssertions(
        assignments=[
            RoleAssignmentCreate(
                user=USER_PERMIT.key,
                role=COMMENTER,
                resource_instance=f"{FOLDER.key}:rnd",
                tenant=TENANT_PERMIT.key,
            )
        ],
        assertions=[
            # direct access allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="read",
                resource={"type": FOLDER.key, "key": "rnd", "tenant": TENANT_PERMIT.key},
                expected_decision=True,
            ),
            # access to child resources allowed
            *[
                CheckAssertion(
                    user=USER_PERMIT.key,
                    action=action,
                    resource={
                        "type": DOCUMENT.key,
                        "key": instance,
                        "tenant": TENANT_PERMIT.key,
                    },
                    expected_decision=True,
                )
                for action in ["read", "comment"]
                for instance in ["architecture", "opal"]
            ],
            # higher permissions not allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="update",
                resource={
                    "type": DOCUMENT.key,
                    "key": "architecture",
                    "tenant": TENANT_PERMIT.key,
                },
                expected_decision=False,
            ),
            # access to other resources not allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="read",
                resource={"type": DOCUMENT.key, "key": "budget23", "tenant": TENANT_PERMIT.key},
                expected_decision=False,
            ),
        ],
    ),
    # access from highest level (account)
    PermissionAssertions(
        assignments=[
            RoleAssignmentCreate(
                user=USER_PERMIT.key,
                role=ADMIN,
                resource_instance=f"{ACCOUNT.key}:permitio",
                tenant=TENANT_PERMIT.key,
            ),
            RoleAssignmentCreate(
                user=USER_CC.key,
                role=MEMBER,
                resource_instance=f"{ACCOUNT.key}:cocacola",
                tenant=TENANT_CC.key,
            ),
        ],
        assertions=[
            # direct access allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="invite-user",
                resource={"type": ACCOUNT.key, "key": "permitio", "tenant": TENANT_PERMIT.key},
                expected_decision=True,
            ),
            # access to child resources allowed
            *[
                CheckAssertion(
                    user=USER_PERMIT.key,
                    action=action,
                    resource={
                        "type": DOCUMENT.key,
                        "key": instance,
                        "tenant": TENANT_PERMIT.key,
                    },
                    expected_decision=True,
                    pre_assertion_hook=lambda permit: permit.api.resource_roles.update_role_derivation_conditions(
                        resource_key=FOLDER.key,
                        role_key=EDITOR,
                        conditions=PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings(
                            no_direct_roles_on_object=False
                        ),
                    ),
                    post_assertion_hook=lambda permit: permit.api.resource_roles.update_role_derivation_conditions(
                        resource_key=FOLDER.key,
                        role_key=EDITOR,
                        conditions=PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings(
                            no_direct_roles_on_object=True
                        ),
                    ),
                )
                for action in ["read", "comment", "update", "delete"]
                for instance in ["architecture", "opal", "budget23", "june-expenses"]
            ],
            *[
                # access to other tenants not allowed
                CheckAssertion(
                    user=USER_PERMIT.key,
                    action=action,
                    resource={
                        "type": DOCUMENT.key,
                        "key": "secret-recipe",
                        "tenant": TENANT_CC.key,
                    },
                    expected_decision=False,
                )
                for action in ["read", "comment"]
            ],
            *[
                # but access is allowed to user with lower permissions in the right tenant
                CheckAssertion(
                    user=USER_CC.key,
                    action=action,
                    resource={
                        "type": DOCUMENT.key,
                        "key": "secret-recipe",
                        "tenant": TENANT_CC.key,
                    },
                    expected_decision=True,
                )
                for action in ["read", "comment"]
            ],
        ],
    ),
    # permissions from higher level blocked by condition on role derivation
    PermissionAssertions(
        assignments=[
            RoleAssignmentCreate(
                user=USER_PERMIT.key,
                role=ADMIN,
                resource_instance=f"{ACCOUNT.key}:permitio",
                tenant=TENANT_PERMIT.key,
            ),
            RoleAssignmentCreate(
                user=USER_PERMIT.key,
                role=VIEWER,
                resource_instance=f"{FOLDER.key}:rnd",
                tenant=TENANT_PERMIT.key,
            ),
        ],
        assertions=[
            # direct access allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="read",
                resource={"type": FOLDER.key, "key": "rnd", "tenant": TENANT_PERMIT.key},
                expected_decision=True,
            ),
            # access given by derived role is not allowed
            *[
                CheckAssertion(
                    user=USER_PERMIT.key,
                    action=action,
                    resource={
                        "type": FOLDER.key,
                        "key": "rnd",
                        "tenant": TENANT_PERMIT.key,
                    },
                    expected_decision=False,
                )
                for action in ["rename", "delete", "create-document"]
            ],
        ],
    ),
    # permissions from higher level blocked by condition on role derivation rule
    PermissionAssertions(
        assignments=[
            RoleAssignmentCreate(
                user=USER_PERMIT.key,
                role=MEMBER,
                resource_instance=f"{ACCOUNT.key}:permitio",
                tenant=TENANT_PERMIT.key,
            ),
            RoleAssignmentCreate(
                user=USER_PERMIT.key,
                role=VIEWER,
                resource_instance=f"{FOLDER.key}:rnd",
                tenant=TENANT_PERMIT.key,
            ),
        ],
        assertions=[
            # direct access allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="read",
                resource={"type": FOLDER.key, "key": "rnd", "tenant": TENANT_PERMIT.key},
                expected_decision=True,
            ),
            # access given by derived role is not allowed
            CheckAssertion(
                user=USER_PERMIT.key,
                action="rename",
                resource={
                    "type": FOLDER.key,
                    "key": "rnd",
                    "tenant": TENANT_PERMIT.key,
                },
                expected_decision=False,
            ),
        ],
    ),
]


async def cleanup(permit: Permit):
    logger.debug("Running cleanup...")
    try:
        for user in CREATED_USERS:
            try:
                await permit.api.users.delete(user.key)
            except PermitApiError as error:
                if error.status_code == 404:
                    logger.debug(f"SKIPPING delete, user does not exist: {user.key}")
        for tenant in CREATED_TENANTS:
            try:
                await permit.api.tenants.delete(tenant.key)
            except PermitApiError as error:
                if error.status_code == 404:
                    logger.debug(f"SKIPPING delete, tenant does not exist: {tenant.key}")
        for rel_tuple in RELATIONSHIPS:
            subject, relation, object, tenant = rel_tuple
            try:
                await permit.api.relationship_tuples.delete(
                    RelationshipTupleDelete(subject=subject, relation=relation, object=object)
                )
            except PermitApiError as error:
                if error.status_code == 404:
                    logger.debug(
                        f"SKIPPING delete, rel tuple does not exist: ({subject}, {relation}, {object}, {tenant})"
                    )
        for assertion in ASSIGNMENTS_AND_ASSERTIONS:
            for assignment in assertion.assignments:
                try:
                    await permit.api.role_assignments.unassign(
                        RoleAssignmentRemove(
                            user=assignment.user,
                            role=assignment.role,
                            resource_instance=assignment.resource_instance,
                            tenant=assignment.tenant,
                        )
                    )
                except PermitApiError as error:
                    if error.status_code == 404:
                        logger.debug(
                            f"SKIPPING delete, role assignment does not exist: ({assignment.user}, {assignment.role}, "
                            f"{assignment.resource_instance}, {assignment.tenant})"
                        )
        for resource in CREATED_RESOURCES:
            try:
                await permit.api.resources.delete(resource.key)
            except PermitApiError as error:
                if error.status_code == 404:
                    logger.debug(f"SKIPPING delete, resource does not exist: {resource.key}")
    except PermitApiError as error:
        handle_api_error(error, "Got API Error during cleanup")
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error during cleanup: {error}")
        pytest.fail(f"Got error during cleanup: {error}")
    logger.debug("Cleanup finished.")


async def assert_permit_check(permit: Permit, q: CheckAssertion):
    logger.info(f"asserting: permit.check({q.user}, {q.action}, {q.resource!s}) === {q.expected_decision!s}")
    decision = await permit.check(q.user, q.action, q.resource)
    assert q.expected_decision == decision


async def assert_permit_authorized_users(permit: Permit, q: CheckAssertion, assignments: list[RoleAssignmentCreate]):
    logger.info(
        f"asserting: permit.authorized_users({q.action}, {q.resource}) === {q.expected_decision}",
    )
    authorized_users = await permit.authorized_users(q.action, q.resource)
    assert authorized_users.tenant == q.resource["tenant"]
    assert authorized_users.resource == f"{q.resource['type']}:{q.resource['key']}"
    if q.expected_decision is True:
        assert q.user in authorized_users.users
        for assignment in authorized_users.users[q.user]:
            assert any(
                (
                    assignment.role.split("#")[1] == created_assignment.role
                    and assignment.tenant == created_assignment.tenant
                    and assignment.user == created_assignment.user
                    and assignment.resource == created_assignment.resource_instance
                )
                for created_assignment in assignments
            )
    else:
        assert q.user not in authorized_users.users


async def test_rebac_policy(permit: Permit):
    logger.info("initial setup of objects")
    await cleanup(permit)
    try:
        # schema --------------------------------------------------------------

        # create resources
        for resource_data in CREATED_RESOURCES:
            logger.debug(f"creating resource: {resource_data.key}")
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
                logger.debug(f"creating resource role: {resource_key}#{role_data.key}")
                role = await permit.api.resource_roles.create(resource_key=resource_key, role_data=role_data)
                assert role is not None
                assert role.key == role_data.key
                assert role.name == role_data.name
                assert role.description == role_data.description
                assert role.permissions is not None
                assert len(role.permissions) == len(role_data.permissions)

        # create resource relations
        for resource_key, resource_relations in iter(RESOURCE_RELATIONS.items()):
            for relation_data in resource_relations:
                logger.debug(f"creating resource relation: {resource_key}->{relation_data.key}")
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
            logger.debug(
                f"creating derivation: {derivation_data.source_role} -> {derivation_data.derived_role} "
                f"(via {derivation_data.via_relation})"
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

        # data ----------------------------------------------------------------

        # create tenants
        for tenant_data in CREATED_TENANTS:
            logger.debug(f"creating tenant: {tenant_data.key}")
            tenant = await permit.api.tenants.create(tenant_data)
            assert tenant is not None
            assert tenant.key == tenant_data.key
            assert tenant.name == tenant_data.name
            assert tenant.description is None

        # create users
        for user_data in CREATED_USERS:
            logger.debug(f"creating user: {user_data.key}")
            user = await permit.api.users.create(user_data)
            assert user is not None
            assert user.key == user_data.key
            assert user.email == user_data.email
            assert user.first_name == user_data.first_name
            assert user.last_name == user_data.last_name
            assert set(user.attributes.keys()) == set(user_data.attributes.keys())

        # relationship tuples
        for tuple_data in RELATIONSHIPS:
            subject, relation, object, tenant = tuple_data
            logger.debug(f"creating relationship tuple: ({subject}, {relation}, {object}, {tenant})")
            rel_tuple = await permit.api.relationship_tuples.create(
                RelationshipTupleCreate(subject=subject, relation=relation, object=object, tenant=tenant)
            )
            assert rel_tuple is not None
            assert rel_tuple.subject == subject
            assert rel_tuple.relation == relation
            assert rel_tuple.object == object
            assert rel_tuple.tenant == tenant

        tuples = await permit.api.relationship_tuples.list()
        len_tuples = len(tuples)
        logger.debug(f"there are currently {len_tuples} relationship tuples in the system")

        # bulk create relationship tuples
        bulk_relationships_to_create = [
            RelationshipTupleCreate(subject=subject, relation=relation, object=object, tenant=tenant)
            for (subject, relation, object, tenant) in BULK_RELATIONSHIPS
        ]
        bulk_relationships_to_delete = [
            RelationshipTupleDelete(subject=subject, relation=relation, object=object)
            for (subject, relation, object, tenant) in BULK_RELATIONSHIPS
        ]

        for instance_key in BULK_RELATIONSHIPS_INSTANCES:
            parts = instance_key.split(":")
            logger.debug(f"creating resource instance: {instance_key}")
            await permit.api.resource_instances.create(
                ResourceInstanceCreate(key=parts[1], resource=parts[0], tenant=TENANT_PERMIT.key)
            )

        async def create_relationships_in_bulk():
            await permit.api.relationship_tuples.bulk_create(tuples=bulk_relationships_to_create)

            tuples = await permit.api.relationship_tuples.list()
            assert len(tuples) == len_tuples + len(BULK_RELATIONSHIPS)
            logger.debug(f"there are currently {len(tuples)} relationship tuples in the system")

        async def remove_relationships_in_bulk():
            await permit.api.relationship_tuples.bulk_delete(tuples=bulk_relationships_to_delete)

            tuples = await permit.api.relationship_tuples.list()
            assert len(tuples) == len_tuples
            logger.debug(f"there are currently {len(tuples)} relationship tuples in the system")

        logger.debug(f"creating {len(BULK_RELATIONSHIPS)} relationship tuples in bulk: {BULK_RELATIONSHIPS!s}")
        await create_relationships_in_bulk()

        logger.debug(f"removing the same {len(BULK_RELATIONSHIPS)} relationship tuples in bulk: {BULK_RELATIONSHIPS!s}")
        await remove_relationships_in_bulk()

        # assign roles and then run permission checks
        for test_step in ASSIGNMENTS_AND_ASSERTIONS:
            try:
                # role assignments
                for assignment in test_step.assignments:
                    logger.debug(
                        f"creating role assignment: ({assignment.user}, {assignment.role}, "
                        f"{assignment.resource_instance}) in tenant: {assignment.tenant}"
                    )
                    ra = await permit.api.role_assignments.assign(assignment)
                    assert ra.user == assignment.user
                    assert ra.role == assignment.role
                    assert ra.resource_instance == assignment.resource_instance
                    assert ra.tenant == assignment.tenant

                logger.info(
                    "sleeping 10 seconds before permit checks to make sure all writes propagated from cloud to PDP"
                )
                await asyncio.sleep(10)

                for assertion in test_step.assertions:
                    if assertion.pre_assertion_hook is not None:
                        logger.debug("executing pre assertion hook")
                        await assertion.pre_assertion_hook(permit)
                        await asyncio.sleep(1)
                    await assert_permit_check(permit, assertion)
                    await assert_permit_authorized_users(permit, assertion, test_step.assignments)
                    if assertion.post_assertion_hook is not None:
                        logger.debug("executing post assertion hook")
                        await assertion.post_assertion_hook(permit)
                        await asyncio.sleep(1)
            finally:
                for assignment in test_step.assignments:
                    try:
                        logger.debug(
                            f"deleting role assignment: ({assignment.user}, {assignment.role}, "
                            f"{assignment.resource_instance}) in tenant: {assignment.tenant}"
                        )
                        await permit.api.role_assignments.unassign(
                            RoleAssignmentRemove(
                                user=assignment.user,
                                role=assignment.role,
                                resource_instance=assignment.resource_instance,
                                tenant=assignment.tenant,
                            )
                        )
                    except PermitApiError as error:
                        if error.status_code == 404:
                            logger.debug(
                                f"SKIPPING delete, role assignment does not exist: "
                                f"({assignment.user}, {assignment.role}, "
                                f"{assignment.resource_instance}, {assignment.tenant})"
                            )
                        else:
                            raise
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        await cleanup(permit)
