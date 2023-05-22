import pytest
from loguru import logger

from permit import Permit
from permit.exceptions import PermitApiError
from tests.utils import handle_api_error

TEST_RESOURCE_KEY = "test"
TEST_ADMIN_ROLE_KEY = "testadmin"
TEST_EMPTY_ROLE_KEY = "emptyrole"
CREATED_RESOURCES = [TEST_RESOURCE_KEY]
CREATED_ROLES = [TEST_ADMIN_ROLE_KEY, TEST_EMPTY_ROLE_KEY]


async def test_roles(permit: Permit):
    logger.info("initial setup of objects")
    len_roles_original = 0
    try:
        test_resource = await permit.api.resources.create(
            {
                "key": TEST_RESOURCE_KEY,
                "name": TEST_RESOURCE_KEY,
                "urn": "prn:gdrive:test",
                "actions": {
                    "create": {},
                    "read": {},
                    "update": {},
                    "delete": {},
                },
            }
        )

        # initial number of roles
        roles = await permit.api.roles.list()
        len_roles_original = len(roles)

        # create admin role
        admin = await permit.api.roles.create(
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

        assert admin is not None
        assert admin.key == TEST_ADMIN_ROLE_KEY
        assert admin.name == TEST_ADMIN_ROLE_KEY
        assert admin.description == "a test role"
        assert admin.permissions is not None
        assert f"{TEST_RESOURCE_KEY}:create" in admin.permissions
        assert f"{TEST_RESOURCE_KEY}:read" in admin.permissions

        # increased number of roles by 1
        roles = await permit.api.roles.list()
        assert len(roles) == len_roles_original + 1
        # can find new role in the new list
        assert len([r for r in roles if r.key == admin.key]) == 1

        # get non existing role -> 404
        with pytest.raises(PermitApiError) as e:
            await permit.api.roles.get("nosuchrole")
        assert e.value.status_code == 404

        # create existing role -> 409
        with pytest.raises(PermitApiError) as e:
            await permit.api.roles.create(
                {
                    "key": TEST_ADMIN_ROLE_KEY,
                    "name": "TestAdmin2",
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

        roles = await permit.api.roles.list()
        assert len(roles) == len_roles_original + 2

        # assign permissions to roles
        assigned_empty = await permit.api.roles.assign_permissions(
            TEST_EMPTY_ROLE_KEY, [f"{TEST_RESOURCE_KEY}:delete"]
        )

        assert assigned_empty.key == empty.key
        assert len(assigned_empty.permissions) == 1
        assert f"{TEST_RESOURCE_KEY}:delete" in assigned_empty.permissions

        # remove permissions from role
        await permit.api.roles.remove_permissions(
            TEST_ADMIN_ROLE_KEY, [f"{TEST_RESOURCE_KEY}:create"]
        )

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

    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        # cleanup
        try:
            for resource_key in CREATED_RESOURCES:
                await permit.api.resources.delete(resource_key)
            for role_key in CREATED_ROLES:
                await permit.api.roles.delete(role_key)
            assert len(await permit.api.roles.list()) == len_roles_original
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except Exception as error:
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")
