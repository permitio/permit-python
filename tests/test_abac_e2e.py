import time
from typing import List

import pytest
from loguru import logger

from permit import Permit, RoleAssignmentRead
from permit.api.models import (
    AttributeType,
    ConditionSetCreate,
    ConditionSetRuleCreate,
    ConditionSetType,
    ResourceAttributeCreate,
    RoleCreate,
    TenantCreate,
    UserCreate,
)
from permit.exceptions import PermitApiError, PermitConnectionError

from .utils import handle_api_error


def print_break():
    print("\n\n ----------- \n\n")


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
USER_C = UserCreate(
    key="auth0|jane",
    email="jane@permit.io",
    first_name="Jane",
    last_name="Doe",
    attributes={"age": 25},
)

ADMIN = RoleCreate(
    key="admin", name="Admin", permissions=["document:create", "document:read"]
)
VIEWER = RoleCreate(key="viewer", name="Viewer", permissions=["document:read"])

TESLA = TenantCreate(key="tesla", name="Tesla Inc")

# condition sets
USERS_OVER_30 = ConditionSetCreate(
    key="users_over_thirty",
    type=ConditionSetType.userset,
    name="Users over 30",
    conditions={"allOf": [{"allOf": [{"user.age": {"greater-than": 30}}]}]},
)
PRIVATE_DOCS = ConditionSetCreate(
    key="private_docs",
    type=ConditionSetType.resourceset,
    resource_id=None,
    name="Private docs",
    conditions={"allOf": [{"allOf": [{"resource.private": {"equals": False}}]}]},
)

CONDITION_SETS = [USERS_OVER_30, PRIVATE_DOCS]

CREATED_USERS = [USER_A, USER_B, USER_C]
CREATED_TENANTS = [TESLA]
CREATED_ROLES = [ADMIN, VIEWER]

RBAC_SLEEP_TIME = 5
ABAC_SLEEP_TIME = 60


async def test_abac_e2e(permit: Permit):
    logger.info("initial setup of objects")
    try:
        document = await permit.api.resources.create(
            {
                "key": "document",
                "name": "Document",
                "urn": "prn:gdrive:document",
                "description": "google drive document",
                "actions": {
                    "create": {},
                    "read": {},
                    "update": {},
                    "delete": {},
                    "sign": {},
                },
                "attributes": {
                    "private": {
                        "type": "bool",
                        "description": "whether the document is private",
                    },
                },
            }
        )

        # verify create output
        assert document is not None
        assert document.id is not None

        PRIVATE_DOCS.resource_id = document.id.hex

        assert document.key == "document"
        assert document.name == "Document"
        assert document.description == "google drive document"
        assert document.urn == "prn:gdrive:document"
        assert len(document.actions or {}) == 5
        assert (document.actions or {}).get("create") is not None
        assert (document.actions or {}).get("read") is not None
        assert (document.actions or {}).get("update") is not None
        assert (document.actions or {}).get("delete") is not None
        assert (document.actions or {}).get("sign") is not None

        # verify list output
        resources = await permit.api.resources.list()
        assert len(resources) == 1
        assert resources[0].id == document.id
        assert resources[0].key == document.key
        assert resources[0].name == document.name
        assert resources[0].description == document.description
        assert resources[0].urn == document.urn

        # create user attributes
        try:
            await permit.api.resource_attributes.create(
                "__user", ResourceAttributeCreate(key="age", type=AttributeType.number)
            )
        except PermitApiError as e:
            if e.status_code != 409:  # ignore already created
                raise

        # create tenants
        for tenant_data in CREATED_TENANTS:
            tenant = await permit.api.tenants.create(tenant_data)
            assert tenant is not None
            assert tenant.key == tenant_data.key
            assert tenant.name == tenant_data.name
            assert tenant.description is None

        # create users
        for user_data in CREATED_USERS:
            user = await permit.api.users.sync(user_data)
            assert user is not None
            assert user.key == user_data.key
            assert user.email == user_data.email
            assert user.first_name == user_data.first_name
            assert user.last_name == user_data.last_name
            assert set(user.attributes.keys()) == set(user_data.attributes.keys())

        # create role
        for role_data in CREATED_ROLES:
            await permit.api.roles.create(role_data)

        # assign role to user in tenant
        await permit.api.users.assign_role(
            {
                "user": USER_A.key,
                "role": ADMIN.key,
                "tenant": TESLA.key,
            }
        )

        await permit.api.users.assign_role(
            {
                "user": USER_B.key,
                "role": ADMIN.key,
                "tenant": TESLA.key,
            }
        )

        logger.info(
            f"sleeping {RBAC_SLEEP_TIME} seconds before permit.check() to make sure all writes propagated from cloud to PDP"
        )
        time.sleep(RBAC_SLEEP_TIME)

        # testing Admin permissions
        logger.info("testing admin permissions")
        assert await permit.check(
            USER_A.key,
            "create",
            {"type": "document", "tenant": TESLA.key},
        )
        assert await permit.check(
            USER_B.key,
            "create",
            {"type": "document", "tenant": TESLA.key},
        )

        assert not await permit.check(
            USER_A.key,
            "sign",
            {"type": "document", "tenant": TESLA.key},
        )
        assert not await permit.check(
            USER_B.key,
            "sign",
            {"type": "document", "tenant": TESLA.key},
        )

        print_break()

        logger.info("creating condition sets")
        for condition_set_data in CONDITION_SETS:
            condition_set = await permit.api.condition_sets.create(condition_set_data)
            assert condition_set.key == condition_set_data.key
            assert condition_set.type == condition_set_data.type

        condition_sets = await permit.api.condition_sets.list()
        assert len(condition_sets) == 2

        await permit.api.condition_set_rules.create(
            ConditionSetRuleCreate(
                user_set=USERS_OVER_30.key,
                permission="document:sign",
                resource_set=PRIVATE_DOCS.key,
            )
        )

        rules = await permit.api.condition_set_rules.list()
        assert len(rules) == 1

        print_break()

        logger.info(
            f"sleeping {ABAC_SLEEP_TIME} seconds before permit.check() to make sure all writes propagated from cloud to PDP"
        )
        time.sleep(ABAC_SLEEP_TIME)

        def abac_user(user: UserCreate):
            return user.dict(exclude={"first_name", "last_name"})

        logger.info("testing that users over 30 can sign public documents")
        assert await permit.check(
            abac_user(USER_A),
            "sign",
            {
                "type": "document",
                "tenant": TESLA.key,
                "attributes": {"private": False},
            },
        )

        logger.info("testing that users under 30 cannot sign public documents")
        assert not await permit.check(
            abac_user(USER_B),
            "sign",
            {
                "type": "document",
                "tenant": TESLA.key,
                "attributes": {"private": False},
            },
        )

        logger.info("testing that users over 30 cannot sign private documents")
        assert not await permit.check(
            abac_user(USER_A),
            "sign",
            {
                "type": "document",
                "tenant": TESLA.key,
                "attributes": {"private": True},
            },
        )

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
            for condition_set in CONDITION_SETS:
                await permit.api.condition_sets.delete(condition_set.key)
            await permit.api.resources.delete("document")
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError as error:
            raise
        except Exception as error:
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")
