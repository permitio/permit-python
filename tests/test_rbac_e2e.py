import asyncio
import time
from typing import Any, AsyncIterable, Awaitable, Callable, Final, List, Optional

import pytest
from loguru import logger
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

from permit import Permit, ResourceRead, RoleAssignmentRead, RoleRead
from permit.exceptions import PermitApiError, PermitConnectionError
from permit.pdp_api.models import RoleAssignment

from .utils import handle_api_error, handle_cleanup_error, unique_key


def print_break():
    print("\n\n ----------- \n\n")  # noqa: T201


TEST_TIMEOUT = 1
# test_api_timeout and test_pdp_timeout run against the local pytest_httpserver
# and need no credentials, so the tests that do are marked e2e one by one rather
# than with a module-level pytestmark.
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

# Every object below is created with a key derived from unique_key(): the whole
# e2e suite shares one environment, so a fixed key like "document" or "admin" is
# shared mutable state that other tests create, assert on and delete.
PER_PAGE: Final[int] = 100
PROPAGATION_TIMEOUT: Final[float] = 30.0
PROPAGATION_INTERVAL: Final[float] = 0.5


async def wait_until(
    condition: Callable[[], Awaitable[bool]],
    description: str,
    timeout: float = PROPAGATION_TIMEOUT,
    interval: float = PROPAGATION_INTERVAL,
) -> None:
    """Poll ``condition`` until it is true, or fail the test.

    Writes reach the PDP asynchronously, and how long that takes depends on the
    environment (local PDP vs cloud) and on how busy it is. A fixed sleep is
    either flaky or slow; polling is neither.
    """
    deadline = time.monotonic() + timeout
    while True:
        if await condition():
            return
        if time.monotonic() >= deadline:
            pytest.fail(f"timed out after {timeout}s waiting for {description}")
        await asyncio.sleep(interval)


async def find_by_key(list_page: Callable[[int], Awaitable[List[Any]]], key: str) -> Optional[Any]:
    """Find an object by key across all pages of a paginated list endpoint.

    The environment is shared, so the object under test is not necessarily on
    the first page and the total count is not something a test may assert on.
    """
    page = 1
    while True:
        items = await list_page(page)
        for item in items:
            if item.key == key:
                return item
        if len(items) < PER_PAGE:
            return None
        page += 1


async def delete_quietly(delete: Callable[[str], Awaitable[None]], key: str, description: str) -> None:
    """Delete one object during teardown, tolerating one that is already gone."""
    try:
        await delete(key)
    except PermitApiError as error:
        handle_cleanup_error(error, f"Got API Error during cleanup of {description} '{key}'")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error during cleanup of {description} '{key}': {error}")
        pytest.fail(f"Got error during cleanup of {description} '{key}': {error}")


async def assert_gone(get: Callable[[str], Awaitable[Any]], key: str, description: str) -> None:
    """Assert the object this test created is really gone after teardown."""
    with pytest.raises(PermitApiError) as exc_info:
        await get(key)
    assert exc_info.value.status_code == 404, f"{description} '{key}' still exists after cleanup"


def sleeping(request: Request):  # noqa: ARG001
    time.sleep(TEST_TIMEOUT + 1)
    return Response("OK", status=200)


async def test_api_timeout(httpserver: HTTPServer):
    mocked_url = httpserver.url_for("").rstrip("/")
    permit = Permit(
        token="mocked",
        pdp=mocked_url,
        api_url=mocked_url,
        api_timeout=TEST_TIMEOUT,
    )
    current_time = time.time()
    httpserver.expect_request("/v2/api-key/scope").respond_with_handler(sleeping)
    with pytest.raises(asyncio.TimeoutError):
        await permit.api.roles.list()
    time_passed = time.time() - current_time
    assert time_passed < 3


async def test_pdp_timeout(httpserver: HTTPServer):
    mocked_url = httpserver.url_for("").rstrip("/")
    permit = Permit(
        token="mocked",
        pdp=mocked_url,
        api_url=mocked_url,
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
    resource_key = unique_key("document")
    admin_role_key = unique_key("admin")
    viewer_role_key = unique_key("viewer")
    admin_role_permissions = [
        f"{resource_key}:{RESOURCE_CREATE_ACTION}",
        f"{resource_key}:{RESOURCE_READ_ACTION}",
    ]
    viewer_role_permissions = [f"{resource_key}:{RESOURCE_READ_ACTION}"]
    try:
        document = await permit.api.resources.create(
            {
                "key": resource_key,
                "name": "Document",
                "urn": f"prn:gdrive:{resource_key}",
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
        # verify create output
        assert document is not None
        assert document.id is not None
        assert document.key == resource_key
        assert document.name == "Document"
        assert document.description == "google drive document"
        assert document.urn == f"prn:gdrive:{resource_key}"
        assert len(document.actions or {}) == len(RESOURCE_ACTIONS)
        for action in RESOURCE_ACTIONS:
            assert (document.actions or {}).get(action) is not None

        # verify list output: the resource this test created is listed, with the
        # same contents the create call returned.
        listed_document = await find_by_key(
            lambda page: permit.api.resources.list(page=page, per_page=PER_PAGE), resource_key
        )
        assert listed_document is not None, f"resource '{resource_key}' is missing from the resource list"
        assert listed_document.id == document.id
        assert listed_document.key == document.key
        assert listed_document.name == document.name
        assert listed_document.description == document.description
        assert listed_document.urn == document.urn

        # create admin role
        admin = await permit.api.roles.create(
            {
                "key": admin_role_key,
                "name": "Admin",
                "description": "an admin role",
                "permissions": admin_role_permissions,
            }
        )
        assert admin is not None
        assert admin.key == admin_role_key
        assert admin.name == "Admin"
        assert admin.description == "an admin role"
        assert len(admin.permissions or []) == len(admin_role_permissions)
        for permission in admin_role_permissions:
            assert permission in admin.permissions

        # create viewer role
        viewer = await permit.api.roles.create(
            {
                "key": viewer_role_key,
                "name": "Viewer",
                "description": "an viewer role",
            }
        )
        assert viewer is not None
        assert viewer.key == viewer_role_key
        assert viewer.name == "Viewer"
        assert viewer.description == "an viewer role"
        assert viewer.permissions is not None
        assert len(viewer.permissions) == 0

        # assign permissions to roles
        assigned_viewer = await permit.api.roles.assign_permissions(viewer_role_key, viewer_role_permissions)

        assert assigned_viewer.key == viewer_role_key
        assert len(assigned_viewer.permissions or []) == len(viewer_role_permissions)
        for permission in viewer_role_permissions:
            assert permission in assigned_viewer.permissions
        yield document, admin, viewer
    finally:
        # cleanup: each object is deleted on its own, so one already-gone object
        # does not leak the rest into the shared environment.
        await delete_quietly(permit.api.roles.delete, admin_role_key, "role")
        await delete_quietly(permit.api.roles.delete, viewer_role_key, "role")
        await delete_quietly(permit.api.resources.delete, resource_key, "resource")
        await assert_gone(permit.api.roles.get, admin_role_key, "role")
        await assert_gone(permit.api.roles.get, viewer_role_key, "role")
        await assert_gone(permit.api.resources.get, resource_key, "resource")


@pytest.mark.e2e
async def test_permission_check_e2e(
    permit: Permit,
    setup_env: tuple[ResourceRead, RoleRead, RoleRead],
):
    document, admin, viewer = setup_env
    tenant_key = unique_key("tesla")
    user_key = unique_key("auth0|elon")
    try:
        # create a tenant
        tenant = await permit.api.tenants.create(
            {
                "key": tenant_key,
                "name": "Tesla Inc",
                "description": "The car company",
            }
        )

        assert tenant.key == tenant_key
        assert tenant.name == "Tesla Inc"
        assert tenant.description == "The car company"
        assert tenant.attributes is None or len(tenant.attributes) == 0

        # create a user
        user = await permit.api.users.sync(
            {
                "key": user_key,
                "email": "elonmusk@tesla.com",
                "first_name": "Elon",
                "last_name": "Musk",
                "attributes": {
                    "age": 50,
                    "favoriteColor": "red",
                },
            }
        )

        assert user.key == user_key
        assert user.email == "elonmusk@tesla.com"
        assert user.first_name == "Elon"
        assert user.last_name == "Musk"
        assert len(user.attributes or {}) == 2
        assert user.attributes["age"] == 50
        assert user.attributes["favoriteColor"] == "red"

        # assign role to user in tenant
        ra = await permit.api.users.assign_role(
            {
                "user": user_key,
                "role": viewer.key,
                "tenant": tenant_key,
            }
        )

        assert ra.user_id == user.id
        assert ra.role_id == viewer.id
        assert ra.tenant_id == tenant.id
        assert ra.user == user.email or ra.user == user.key
        assert ra.role == viewer.key
        assert ra.tenant == tenant.key

        logger.info("waiting for the viewer role assignment to propagate to the PDP")
        resource_attributes = {"secret": True}

        # positive permission check (will be True because elon is a viewer, and a viewer can read a document)
        logger.info("testing positive permission check")
        await wait_until(
            lambda: permit.check(
                user_key,
                RESOURCE_READ_ACTION,
                {
                    "type": document.key,
                    "tenant": tenant_key,
                    "attributes": resource_attributes,
                },
            ),
            f"user '{user_key}' to be allowed to read '{document.key}'",
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
        assert not await permit.check(
            user.key,
            RESOURCE_CREATE_ACTION,
            {"type": document.key, "tenant": tenant.key},
        )

        print_break()

        logger.info("testing bulk permission check")
        assert (
            await permit.bulk_check(
                [
                    {
                        "user": user_key,
                        "action": RESOURCE_READ_ACTION,
                        "resource": {
                            "type": document.key,
                            "tenant": tenant_key,
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
        # scoped to this test's user and tenant: the environment is shared, so
        # the unfiltered list contains every other test's assignments too.
        assignments_returned: List[RoleAssignment] = await permit.pdp_api.role_assignments.list(
            user_key=user.key, tenant_key=tenant.key
        )
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
        assigned_roles: List[RoleAssignmentRead] = await permit.api.users.get_assigned_roles(user=user.key)

        assert len(assigned_roles) == 1
        assert assigned_roles[0].user_id == user.id
        assert assigned_roles[0].role_id == admin.id
        assert assigned_roles[0].tenant_id == tenant.id

        # run the same negative permission check again, this time it's True
        logger.info("testing previously negative permission check, should now be positive")
        await wait_until(
            lambda: permit.check(
                user.dict(),
                RESOURCE_CREATE_ACTION,
                {"type": document.key, "tenant": tenant.key},
            ),
            f"user '{user_key}' to be allowed to create '{document.key}' after the role change",
        )

        print_break()
        logger.info("testing get authorized users")
        authorized_users = await permit.authorized_users(
            RESOURCE_CREATE_ACTION, {"type": document.key, "tenant": tenant.key}
        )
        assert authorized_users.tenant == tenant.key
        assert authorized_users.resource == f"{document.key}:*"
        # the resource and the tenant are unique to this test, so this test's
        # user is the only one that can be authorized on them.
        assert len(authorized_users.users) == 1
        assert user.key in authorized_users.users
        assignments_authorized = authorized_users.users[user.key]
        assert len(assignments_authorized) == 1
        assert assignments_authorized[0].user == user.key
        assert assignments_authorized[0].role == admin.key
        assert assignments_authorized[0].tenant == tenant.key
        assert assignments_authorized[0].resource == f"__tenant:{tenant.key}"
        print_break()
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        # cleanup
        await delete_quietly(permit.api.tenants.delete, tenant_key, "tenant")
        await delete_quietly(permit.api.users.delete, user_key, "user")
        await assert_gone(permit.api.tenants.get, tenant_key, "tenant")
        await assert_gone(permit.api.users.get, user_key, "user")


@pytest.mark.e2e
async def test_local_facts_uploader_permission_check_e2e(
    permit: Permit,
    setup_env: tuple[ResourceRead, RoleRead, RoleRead],
):
    permit._config.proxy_facts_via_pdp = True
    assert permit.api.users.config.proxy_facts_via_pdp is True
    document, admin, viewer = setup_env
    tenant_key = unique_key("tesla")
    user_key = unique_key("auth0|elon")
    try:
        with permit.wait_for_sync() as permit:
            # create a tenant
            tenant = await permit.api.tenants.create(
                {
                    "key": tenant_key,
                    "name": "Tesla Inc",
                    "description": "The car company",
                }
            )

            assert tenant.key == tenant_key
            assert tenant.name == "Tesla Inc"
            assert tenant.description == "The car company"
            assert tenant.attributes is None or len(tenant.attributes) == 0

            # create a user
            user = await permit.api.users.sync(
                {
                    "key": user_key,
                    "email": "elonmusk@tesla.com",
                    "first_name": "Elon",
                    "last_name": "Musk",
                    "attributes": {
                        "age": 50,
                        "favoriteColor": "red",
                    },
                }
            )

            assert user.key == user_key
            assert user.email == "elonmusk@tesla.com"
            assert user.first_name == "Elon"
            assert user.last_name == "Musk"
            assert len(user.attributes or {}) == 2
            assert user.attributes["age"] == 50
            assert user.attributes["favoriteColor"] == "red"

            # assign role to user in tenant
            ra = await permit.api.users.assign_role(
                {
                    "user": user_key,
                    "role": viewer.key,
                    "tenant": tenant_key,
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
            # the facts were written through the PDP with wait_for_sync, so they
            # are already in the PDP cache -- but the role's permissions were
            # written through the API and still have to propagate.
            await wait_until(
                lambda: permit.check(
                    user_key,
                    RESOURCE_READ_ACTION,
                    {
                        "type": document.key,
                        "tenant": tenant_key,
                        "attributes": resource_attributes,
                    },
                ),
                f"user '{user_key}' to be allowed to read '{document.key}'",
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
            assert not await permit.check(
                user.key,
                RESOURCE_CREATE_ACTION,
                {"type": document.key, "tenant": tenant.key},
            )

            print_break()

            logger.info("testing bulk permission check")
            assert (
                await permit.bulk_check(
                    [
                        {
                            "user": user_key,
                            "action": RESOURCE_READ_ACTION,
                            "resource": {
                                "type": document.key,
                                "tenant": tenant_key,
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
            assigned_roles: List[RoleAssignmentRead] = await permit.api.users.get_assigned_roles(user=user.key)

            assert len(assigned_roles) == 1
            assert assigned_roles[0].user_id == user.id
            assert assigned_roles[0].role_id == admin.id
            assert assigned_roles[0].tenant_id == tenant.id

            # run the same negative permission check again, this time it's True
            logger.info("testing previously negative permission check, should now be positive")
            await wait_until(
                lambda: permit.check(
                    user.dict(),
                    RESOURCE_CREATE_ACTION,
                    {"type": document.key, "tenant": tenant.key},
                ),
                f"user '{user_key}' to be allowed to create '{document.key}' after the role change",
            )

            print_break()
            logger.info("testing get authorized users")
            authorized_users = await permit.authorized_users(
                RESOURCE_CREATE_ACTION, {"type": document.key, "tenant": tenant.key}
            )
            assert authorized_users.tenant == tenant.key
            assert authorized_users.resource == f"{document.key}:*"
            # the resource and the tenant are unique to this test, so this test's
            # user is the only one that can be authorized on them.
            assert len(authorized_users.users) == 1
            assert user.key in authorized_users.users
            assignments_authorized = authorized_users.users[user.key]
            assert len(assignments_authorized) == 1
            assert assignments_authorized[0].user == user.key
            assert assignments_authorized[0].role == admin.key
            assert assignments_authorized[0].tenant == tenant.key
            assert assignments_authorized[0].resource == f"__tenant:{tenant.key}"
            print_break()
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        raise
    finally:
        # cleanup
        await delete_quietly(permit.api.tenants.delete, tenant_key, "tenant")
        await delete_quietly(permit.api.users.delete, user_key, "user")
        await assert_gone(permit.api.tenants.get, tenant_key, "tenant")
        await assert_gone(permit.api.users.get, user_key, "user")
