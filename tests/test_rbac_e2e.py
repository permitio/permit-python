import asyncio
import time
from typing import AsyncIterable, List

import pytest
from loguru import logger
from pytest_httpserver import HTTPServer
from typing_extensions import Final
from werkzeug import Request, Response

from permit import Permit, ResourceRead, RoleAssignmentRead, RoleRead
from permit.exceptions import PermitApiError, PermitConnectionError
from permit.pdp_api.models import RoleAssignment

from .utils import handle_api_error


def print_break():
    print("\n\n ----------- \n\n")


TEST_TIMEOUT = 1
MOCKED_URL = "http://localhost"
MOCKED_PORT = 9999
RESOURCE_KEY: Final[str] = "document"
RESOURCE_CREATE_ACTION: Final[str] = "create"
RESOURCE_READ_ACTION: Final[str] = "read"
RESOURCE_UPDATE_ACTION: Final[str] = "update"
RESOURCE_DELETE_ACTION: Final[str] = "delete"
RESOURCE_ACTIONS: Final[List[str]] = [
    RESOURCE_CREATE_ACTION,
    RESOURCE_READ_ACTION,
    RESOURCE_UPDATE_ACTION,
    RESOURCE_DELETE_ACTION,
]
ADMIN_ROLE_KEY: Final[str] = "admin"
ADMIN_ROLE_PERMISSIONS: Final[List[str]] = [
    f"{RESOURCE_KEY}:{RESOURCE_CREATE_ACTION}",
    f"{RESOURCE_KEY}:{RESOURCE_READ_ACTION}",
]
VIEWER_ROLE_KEY: Final[str] = "viewer"
VIEWER_ROLE_PERMISSIONS: Final[List[str]] = [f"{RESOURCE_KEY}:{RESOURCE_READ_ACTION}"]
TENANT_KEY: Final[str] = "tesla"
USER_KEY: Final[str] = "auth0|elon"


def sleeping(request: Request):
    time.sleep(TEST_TIMEOUT + 1)
    return Response("OK", status=200)


@pytest.fixture(scope="session")
def httpserver_listen_address():
    return "localhost", MOCKED_PORT


async def test_api_timeout(httpserver: HTTPServer):
    permit = Permit(
        token="mocked",
        pdp=f"{MOCKED_URL}:{MOCKED_PORT}",
        api_url=f"{MOCKED_URL}:{MOCKED_PORT}",
        api_timeout=TEST_TIMEOUT,
    )
    current_time = time.time()
    httpserver.expect_request("/v2/api-key/scope").respond_with_handler(sleeping)
    with pytest.raises(asyncio.TimeoutError):
        await permit.api.roles.list()
    time_passed = time.time() - current_time
    assert time_passed < 3


async def test_pdp_timeout(httpserver: HTTPServer):
    permit = Permit(
        token="mocked",
        pdp=f"{MOCKED_URL}:{MOCKED_PORT}",
        api_url=f"{MOCKED_URL}:{MOCKED_PORT}",
        pdp_timeout=TEST_TIMEOUT,
    )
    current_time = time.time()
    httpserver.expect_request("/allowed").respond_with_handler(sleeping)
    with pytest.raises(asyncio.TimeoutError):
        await permit.check("user", "action", {"type": "resource", "tenant": "tenant"})
    time_passed = time.time() - current_time
    assert time_passed < 3

    current_time = time.time()
    httpserver.expect_request("/allowed/bulk").respond_with_handler(sleeping)
    with pytest.raises(asyncio.TimeoutError):
        await permit.bulk_check(
            [
                {
                    "user": "user",
                    "action": "action",
                    "resource": {"type": "resource", "tenant": "tenant"},
                }
            ]
        )
    time_passed = time.time() - current_time
    assert time_passed < 3


@pytest.fixture
async def setup_env(
    permit: Permit,
) -> AsyncIterable[tuple[ResourceRead, RoleRead, RoleRead]]:
    logger.info("initial setup of objects")
    is_document_created = False
    is_admin_created = False
    is_viewer_created = False
    try:
        document = await permit.api.resources.create(
            {
                "key": RESOURCE_KEY,
                "name": "Document",
                "urn": "prn:gdrive:document",
                "description": "google drive document",
                "actions": {
                    "create": {},
                    "read": {},
                    "update": {},
                    "delete": {},
                },
                "attributes": {
                    "private": {
                        "type": "bool",
                        "description": "whether the document is private",
                    },
                },
            }
        )
        is_document_created = True
        # verify create output
        assert document is not None
        assert document.id is not None
        assert document.key == RESOURCE_KEY
        assert document.name == "Document"
        assert document.description == "google drive document"
        assert document.urn == f"prn:gdrive:{RESOURCE_KEY}"
        assert len(document.actions or {}) == len(RESOURCE_ACTIONS)
        for action in RESOURCE_ACTIONS:
            assert (document.actions or {}).get(action) is not None

        # verify list output
        resources = await permit.api.resources.list()
        assert len(resources) == 1
        assert resources[0].id == document.id
        assert resources[0].key == document.key
        assert resources[0].name == document.name
        assert resources[0].description == document.description
        assert resources[0].urn == document.urn

        # create admin role
        admin = await permit.api.roles.create(
            {
                "key": ADMIN_ROLE_KEY,
                "name": "Admin",
                "description": "an admin role",
                "permissions": ADMIN_ROLE_PERMISSIONS,
            }
        )
        is_admin_created = True
        assert admin is not None
        assert admin.key == ADMIN_ROLE_KEY
        assert admin.name == "Admin"
        assert admin.description == "an admin role"
        assert len(admin.permissions or []) == len(ADMIN_ROLE_PERMISSIONS)
        for permission in ADMIN_ROLE_PERMISSIONS:
            assert permission in admin.permissions

        # create viewer role
        viewer = await permit.api.roles.create(
            {
                "key": VIEWER_ROLE_KEY,
                "name": "Viewer",
                "description": "an viewer role",
            }
        )
        is_viewer_created = True
        assert viewer is not None
        assert viewer.key == VIEWER_ROLE_KEY
        assert viewer.name == "Viewer"
        assert viewer.description == "an viewer role"
        assert viewer.permissions is not None
        assert len(viewer.permissions) == 0

        # assign permissions to roles
        assigned_viewer = await permit.api.roles.assign_permissions(
            VIEWER_ROLE_KEY, VIEWER_ROLE_PERMISSIONS
        )

        assert assigned_viewer.key == VIEWER_ROLE_KEY
        assert len(assigned_viewer.permissions or []) == len(VIEWER_ROLE_PERMISSIONS)
        for permission in VIEWER_ROLE_PERMISSIONS:
            assert permission in assigned_viewer.permissions
        await asyncio.sleep(10)
        yield document, admin, viewer
    finally:
        # cleanup
        try:
            await permit.api.roles.delete(ADMIN_ROLE_KEY)
            await permit.api.roles.delete(VIEWER_ROLE_KEY)
            await permit.api.resources.delete(RESOURCE_KEY)
            assert len(await permit.api.resources.list()) == 0
            assert len(await permit.api.roles.list()) == 0
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError as error:
            raise
        except Exception as error:
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")


async def test_permission_check_e2e(
    permit: Permit,
    setup_env: tuple[ResourceRead, RoleRead, RoleRead],
):
    document, admin, viewer = setup_env
    try:
        # create a tenant
        tenant = await permit.api.tenants.create(
            {
                "key": TENANT_KEY,
                "name": "Tesla Inc",
                "description": "The car company",
            }
        )

        assert tenant.key == TENANT_KEY
        assert tenant.name == "Tesla Inc"
        assert tenant.description == "The car company"
        assert tenant.attributes is None or len(tenant.attributes) == 0

        # create a user
        user = await permit.api.users.sync(
            {
                "key": USER_KEY,
                "email": "elonmusk@tesla.com",
                "first_name": "Elon",
                "last_name": "Musk",
                "attributes": {
                    "age": 50,
                    "favoriteColor": "red",
                },
            }
        )

        assert user.key == USER_KEY
        assert user.email == "elonmusk@tesla.com"
        assert user.first_name == "Elon"
        assert user.last_name == "Musk"
        assert len(user.attributes or {}) == 2
        assert user.attributes["age"] == 50
        assert user.attributes["favoriteColor"] == "red"

        # assign role to user in tenant
        ra = await permit.api.users.assign_role(
            {
                "user": USER_KEY,
                "role": VIEWER_ROLE_KEY,
                "tenant": TENANT_KEY,
            }
        )

        assert ra.user_id == user.id
        assert ra.role_id == viewer.id
        assert ra.tenant_id == tenant.id
        assert ra.user == user.email or ra.user == user.key
        assert ra.role == viewer.key
        assert ra.tenant == tenant.key

        logger.info(
            "sleeping 2 seconds before permit.check() to make sure all writes propagated from cloud to PDP"
        )
        time.sleep(2)

        # positive permission check (will be True because elon is a viewer, and a viewer can read a document)
        logger.info("testing positive permission check")
        resource_attributes = {"secret": True}
        assert await permit.check(
            USER_KEY,
            RESOURCE_READ_ACTION,
            {
                "type": RESOURCE_KEY,
                "tenant": TENANT_KEY,
                "attributes": resource_attributes,
            },
        )

        print_break()

        logger.info("testing positive permission check with complete user object")
        assert await permit.check(
            user.dict(),
            RESOURCE_READ_ACTION,
            {"type": document.key, "tenant": tenant.key},
        )

        print_break()

        # negative permission check (will be False because a viewer cannot create a document)
        logger.info("testing negative permission check")
        assert (
            await permit.check(
                user.key,
                RESOURCE_CREATE_ACTION,
                {"type": document.key, "tenant": tenant.key},
            )
        ) == False

        print_break()

        logger.info("testing bulk permission check")
        assert (
            await permit.bulk_check(
                [
                    {
                        "user": USER_KEY,
                        "action": RESOURCE_READ_ACTION,
                        "resource": {
                            "type": RESOURCE_KEY,
                            "tenant": TENANT_KEY,
                            "attributes": resource_attributes,
                        },
                    },
                    {
                        "user": user.dict(),
                        "action": RESOURCE_READ_ACTION,
                        "resource": {"type": document.key, "tenant": tenant.key},
                    },
                    {
                        "user": user.key,
                        "action": RESOURCE_CREATE_ACTION,
                        "resource": {"type": document.key, "tenant": tenant.key},
                    },
                ],
                {},
            )
        ) == [True, True, False]

        print_break()

        logger.info("testing list role assignments")
        assignments_returned: List[
            RoleAssignment
        ] = await permit.pdp_api.role_assignments.list()
        assert len(assignments_returned) == 1
        assert assignments_returned[0].user == user.key
        assert assignments_returned[0].role == viewer.key
        assert assignments_returned[0].tenant == tenant.key
        print_break()

        logger.info("changing the user roles")

        # change the user role - assign admin role
        await permit.api.users.assign_role(
            {
                "user": user.key,
                "role": admin.key,
                "tenant": tenant.key,
            }
        )
        # change the user role - remove viewer role
        await permit.api.users.unassign_role(
            {
                "user": user.key,
                "role": viewer.key,
                "tenant": tenant.key,
            }
        )

        # list user roles in all tenants
        assigned_roles: List[
            RoleAssignmentRead
        ] = await permit.api.users.get_assigned_roles(user=user.key)

        assert len(assigned_roles) == 1
        assert assigned_roles[0].user_id == user.id
        assert assigned_roles[0].role_id == admin.id
        assert assigned_roles[0].tenant_id == tenant.id

        logger.info(
            "sleeping 2 seconds before permit.check() to make sure all writes propagated from cloud to PDP"
        )
        time.sleep(2)

        # run the same negative permission check again, this time it's True
        logger.info(
            "testing previously negative permission check, should now be positive"
        )
        assert await permit.check(
            user.dict(),
            RESOURCE_CREATE_ACTION,
            {"type": document.key, "tenant": tenant.key},
        )

        print_break()
        logger.info("testing get authorized users")
        authorized_users = await permit.authorized_users(
            RESOURCE_CREATE_ACTION, {"type": document.key, "tenant": tenant.key}
        )
        assert authorized_users.tenant == tenant.key
        assert authorized_users.resource == f"{document.key}:*"
        assert len(authorized_users.users) == 1
        assert user.key in authorized_users.users.keys()
        assignments_authorized = authorized_users.users[user.key]
        assert len(assignments_authorized) == 1
        assert assignments_authorized[0].user == user.key
        assert assignments_authorized[0].role == admin.key
        assert assignments_authorized[0].tenant == tenant.key
        assert assignments_authorized[0].resource == f"__tenant:{tenant.key}"
        print_break()
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
            await permit.api.tenants.delete(TENANT_KEY)
            await permit.api.users.delete(USER_KEY)
            assert len(await permit.api.tenants.list()) == 1  # the default tenant
            assert len((await permit.api.users.list()).data) == 0
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError as error:
            raise
        except Exception as error:
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")


async def test_local_facts_uploader_permission_check_e2e(
    permit: Permit,
    setup_env: tuple[ResourceRead, RoleRead, RoleRead],
):
    permit._config.proxy_facts_via_pdp = True
    assert permit.api.users.config.proxy_facts_via_pdp is True
    document, admin, viewer = setup_env
    try:
        with permit.wait_for_sync() as permit:
            # create a tenant
            tenant = await permit.api.tenants.create(
                {
                    "key": TENANT_KEY,
                    "name": "Tesla Inc",
                    "description": "The car company",
                }
            )

            assert tenant.key == TENANT_KEY
            assert tenant.name == "Tesla Inc"
            assert tenant.description == "The car company"
            assert tenant.attributes is None or len(tenant.attributes) == 0

            # create a user
            user = await permit.api.users.sync(
                {
                    "key": USER_KEY,
                    "email": "elonmusk@tesla.com",
                    "first_name": "Elon",
                    "last_name": "Musk",
                    "attributes": {
                        "age": 50,
                        "favoriteColor": "red",
                    },
                }
            )

            assert user.key == USER_KEY
            assert user.email == "elonmusk@tesla.com"
            assert user.first_name == "Elon"
            assert user.last_name == "Musk"
            assert len(user.attributes or {}) == 2
            assert user.attributes["age"] == 50
            assert user.attributes["favoriteColor"] == "red"

            # assign role to user in tenant
            ra = await permit.api.users.assign_role(
                {
                    "user": USER_KEY,
                    "role": VIEWER_ROLE_KEY,
                    "tenant": TENANT_KEY,
                }
            )

            assert ra.user_id == user.id
            assert ra.role_id == viewer.id
            assert ra.tenant_id == tenant.id
            assert ra.user == user.email or ra.user == user.key
            assert ra.role == viewer.key
            assert ra.tenant == tenant.key
            # positive permission check (will be True because elon is a viewer, and a viewer can read a document)
            logger.info("testing positive permission check")
            resource_attributes = {"secret": True}
            assert await permit.check(
                USER_KEY,
                RESOURCE_READ_ACTION,
                {
                    "type": RESOURCE_KEY,
                    "tenant": TENANT_KEY,
                    "attributes": resource_attributes,
                },
            )

            print_break()

            logger.info("testing positive permission check with complete user object")
            assert await permit.check(
                user.dict(),
                RESOURCE_READ_ACTION,
                {"type": document.key, "tenant": tenant.key},
            )

            print_break()

            # negative permission check (will be False because a viewer cannot create a document)
            logger.info("testing negative permission check")
            assert (
                await permit.check(
                    user.key,
                    RESOURCE_CREATE_ACTION,
                    {"type": document.key, "tenant": tenant.key},
                )
            ) == False

            print_break()

            logger.info("testing bulk permission check")
            assert (
                await permit.bulk_check(
                    [
                        {
                            "user": USER_KEY,
                            "action": RESOURCE_READ_ACTION,
                            "resource": {
                                "type": RESOURCE_KEY,
                                "tenant": TENANT_KEY,
                                "attributes": resource_attributes,
                            },
                        },
                        {
                            "user": user.dict(),
                            "action": RESOURCE_READ_ACTION,
                            "resource": {"type": document.key, "tenant": tenant.key},
                        },
                        {
                            "user": user.key,
                            "action": RESOURCE_CREATE_ACTION,
                            "resource": {"type": document.key, "tenant": tenant.key},
                        },
                    ],
                    {},
                )
            ) == [True, True, False]

            print_break()

            logger.info("changing the user roles")

            # change the user role - assign admin role
            await permit.api.users.assign_role(
                {
                    "user": user.key,
                    "role": admin.key,
                    "tenant": tenant.key,
                }
            )
            # change the user role - remove viewer role
            await permit.api.users.unassign_role(
                {
                    "user": user.key,
                    "role": viewer.key,
                    "tenant": tenant.key,
                }
            )

            # list user roles in all tenants
            assigned_roles: List[
                RoleAssignmentRead
            ] = await permit.api.users.get_assigned_roles(user=user.key)

            assert len(assigned_roles) == 1
            assert assigned_roles[0].user_id == user.id
            assert assigned_roles[0].role_id == admin.id
            assert assigned_roles[0].tenant_id == tenant.id

            # run the same negative permission check again, this time it's True
            logger.info(
                "testing previously negative permission check, should now be positive"
            )
            assert await permit.check(
                user.dict(),
                RESOURCE_CREATE_ACTION,
                {"type": document.key, "tenant": tenant.key},
            )

            print_break()
            logger.info("testing get authorized users")
            authorized_users = await permit.authorized_users(
                RESOURCE_CREATE_ACTION, {"type": document.key, "tenant": tenant.key}
            )
            assert authorized_users.tenant == tenant.key
            assert authorized_users.resource == f"{document.key}:*"
            assert len(authorized_users.users) == 1
            assert user.key in authorized_users.users.keys()
            assignments_authorized = authorized_users.users[user.key]
            assert len(assignments_authorized) == 1
            assert assignments_authorized[0].user == user.key
            assert assignments_authorized[0].role == admin.key
            assert assignments_authorized[0].tenant == tenant.key
            assert assignments_authorized[0].resource == f"__tenant:{tenant.key}"
            print_break()
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError as error:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        raise
    finally:
        # cleanup
        try:
            await permit.api.tenants.delete(TENANT_KEY)
            await permit.api.users.delete(USER_KEY)
            assert len(await permit.api.tenants.list()) == 1  # the default tenant
            assert len((await permit.api.users.list()).data) == 0
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError as error:
            raise
        except Exception as error:
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")
