import time
from typing import Any, Callable, Final, List, Optional

import pytest
from loguru import logger

from permit import RoleAssignmentRead
from permit.exceptions import PermitApiError, PermitConnectionError
from permit.pdp_api.models import RoleAssignment
from permit.sync import Permit as SyncPermit

from .utils import handle_api_error, handle_cleanup_error, unique_key

pytestmark = pytest.mark.e2e


def print_break():
    print("\n\n ----------- \n\n")  # noqa: T201


# Every object below is created with a key derived from unique_key(): the whole
# e2e suite shares one environment, so a fixed key like "document" or "admin" is
# shared mutable state that other tests create, assert on and delete.
PER_PAGE: Final[int] = 100
PROPAGATION_TIMEOUT: Final[float] = 30.0
PROPAGATION_INTERVAL: Final[float] = 0.5


def wait_until(
    condition: Callable[[], bool],
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
        if condition():
            return
        if time.monotonic() >= deadline:
            pytest.fail(f"timed out after {timeout}s waiting for {description}")
        time.sleep(interval)


def find_by_key(list_page: Callable[[int], List[Any]], key: str) -> Optional[Any]:
    """Find an object by key across all pages of a paginated list endpoint.

    The environment is shared, so the object under test is not necessarily on
    the first page and the total count is not something a test may assert on.
    """
    page = 1
    while True:
        items = list_page(page)
        for item in items:
            if item.key == key:
                return item
        if len(items) < PER_PAGE:
            return None
        page += 1


def delete_quietly(delete: Callable[[str], None], key: str, description: str) -> None:
    """Delete one object during teardown, tolerating one that is already gone."""
    try:
        delete(key)
    except PermitApiError as error:
        handle_cleanup_error(error, f"Got API Error during cleanup of {description} '{key}'")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error during cleanup of {description} '{key}': {error}")
        pytest.fail(f"Got error during cleanup of {description} '{key}': {error}")


def assert_gone(get: Callable[[str], Any], key: str, description: str) -> None:
    """Assert the object this test created is really gone after teardown."""
    with pytest.raises(PermitApiError) as exc_info:
        get(key)
    assert exc_info.value.status_code == 404, f"{description} '{key}' still exists after cleanup"


def test_permission_check_e2e(sync_permit: SyncPermit):
    permit = sync_permit
    logger.info("initial setup of objects")
    resource_key = unique_key("document")
    admin_role_key = unique_key("admin")
    viewer_role_key = unique_key("viewer")
    tenant_key = unique_key("tesla")
    user_key = unique_key("auth0|elon")
    create_permission = f"{resource_key}:create"
    read_permission = f"{resource_key}:read"
    try:
        document = permit.api.resources.create(
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
        assert len(document.actions or {}) == 4
        assert (document.actions or {}).get("create") is not None
        assert (document.actions or {}).get("read") is not None
        assert (document.actions or {}).get("update") is not None
        assert (document.actions or {}).get("delete") is not None

        # verify list output: the resource this test created is listed, with the
        # same contents the create call returned.
        listed_document = find_by_key(
            lambda page: permit.api.resources.list(page=page, per_page=PER_PAGE), resource_key
        )
        assert listed_document is not None, f"resource '{resource_key}' is missing from the resource list"
        assert listed_document.id == document.id
        assert listed_document.key == document.key
        assert listed_document.name == document.name
        assert listed_document.description == document.description
        assert listed_document.urn == document.urn

        # create admin role
        admin = permit.api.roles.create(
            {
                "key": admin_role_key,
                "name": "Admin",
                "description": "an admin role",
                "permissions": [create_permission, read_permission],
            }
        )

        assert admin is not None
        assert admin.key == admin_role_key
        assert admin.name == "Admin"
        assert admin.description == "an admin role"
        assert admin.permissions is not None
        assert create_permission in admin.permissions
        assert read_permission in admin.permissions

        # create viewer role
        viewer = permit.api.roles.create(
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
        assigned_viewer = permit.api.roles.assign_permissions(viewer_role_key, [read_permission])

        assert assigned_viewer.key == viewer_role_key
        assert len(assigned_viewer.permissions) == 1
        assert read_permission in assigned_viewer.permissions
        assert create_permission not in assigned_viewer.permissions

        # create a tenant
        tenant = permit.api.tenants.create(
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
        user = permit.api.users.sync(
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
        ra = permit.api.users.assign_role(
            {
                "user": user_key,
                "role": viewer_role_key,
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
        wait_until(
            lambda: permit.check(
                user_key,
                "read",
                {"type": resource_key, "tenant": tenant_key, "attributes": resource_attributes},
            ),
            f"user '{user_key}' to be allowed to read '{resource_key}'",
        )

        print_break()

        logger.info("testing positive permission check with complete user object")
        assert permit.check(user.dict(), "read", {"type": document.key, "tenant": tenant.key})

        print_break()

        # negative permission check (will be False because a viewer cannot create a document)
        logger.info("testing negative permission check")
        check = permit.check(user.key, "create", {"type": document.key, "tenant": tenant.key})
        assert not check

        print_break()

        logger.info("testing permissions in bulk")
        assert permit.bulk_check(
            [
                {
                    "user": user_key,
                    "action": "read",
                    "resource": {
                        "type": resource_key,
                        "tenant": tenant_key,
                        "attributes": resource_attributes,
                    },
                },
                {
                    "user": user.dict(),
                    "action": "read",
                    "resource": {"type": document.key, "tenant": tenant.key},
                },
                {
                    "user": user.key,
                    "action": "create",
                    "resource": {"type": document.key, "tenant": tenant.key},
                },
            ]
        ) == [True, True, False]

        logger.info("testing list role assignments")
        # scoped to this test's user and tenant: the environment is shared, so
        # the unfiltered list contains every other test's assignments too.
        assignments_returned: List[RoleAssignment] = permit.pdp_api.role_assignments.list(
            user_key=user.key, tenant_key=tenant.key
        )
        assert len(assignments_returned) == 1
        assert assignments_returned[0].user == user.key
        assert assignments_returned[0].role == viewer.key
        assert assignments_returned[0].tenant == tenant.key
        print_break()

        logger.info("changing the user roles")

        # change the user role - assign admin role
        permit.api.users.assign_role(
            {
                "user": user.key,
                "role": admin.key,
                "tenant": tenant.key,
            }
        )
        # change the user role - remove viewer role
        permit.api.users.unassign_role(
            {
                "user": user.key,
                "role": viewer.key,
                "tenant": tenant.key,
            }
        )

        # list user roles in all tenants
        assigned_roles: List[RoleAssignmentRead] = permit.api.users.get_assigned_roles(user=user.key)

        assert len(assigned_roles) == 1
        assert assigned_roles[0].user_id == user.id
        assert assigned_roles[0].role_id == admin.id
        assert assigned_roles[0].tenant_id == tenant.id

        # run the same negative permission check again, this time it's True
        logger.info("testing previously negative permission check, should now be positive")
        wait_until(
            lambda: permit.check(user.dict(), "create", {"type": document.key, "tenant": tenant.key}),
            f"user '{user_key}' to be allowed to create '{resource_key}' after the role change",
        )

        print_break()

    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        # cleanup: each object is deleted on its own, so one already-gone object
        # does not leak the rest into the shared environment.
        delete_quietly(permit.api.resources.delete, resource_key, "resource")
        delete_quietly(permit.api.roles.delete, admin_role_key, "role")
        delete_quietly(permit.api.roles.delete, viewer_role_key, "role")
        delete_quietly(permit.api.tenants.delete, tenant_key, "tenant")
        delete_quietly(permit.api.users.delete, user_key, "user")
        assert_gone(permit.api.resources.get, resource_key, "resource")
        assert_gone(permit.api.roles.get, admin_role_key, "role")
        assert_gone(permit.api.roles.get, viewer_role_key, "role")
        assert_gone(permit.api.tenants.get, tenant_key, "tenant")
        assert_gone(permit.api.users.get, user_key, "user")
