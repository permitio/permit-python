import asyncio
import time
from typing import Any, Awaitable, Callable, Final, List, Optional

import pytest
from loguru import logger

from permit import Permit
from permit.api.models import (
    AttributeType,
    ConditionSetCreate,
    ConditionSetRuleCreate,
    ConditionSetRuleRemove,
    ConditionSetType,
    ResourceAttributeCreate,
    RoleCreate,
    TenantCreate,
    UserCreate,
)
from permit.exceptions import PermitApiError, PermitConnectionError

from .utils import handle_api_error, handle_cleanup_error, unique_key


def print_break():
    print("\n\n ----------- \n\n")  # noqa: T201


PER_PAGE: Final[int] = 100
# RBAC decisions land in the PDP within seconds; an ABAC condition set has to be
# compiled into policy first, which takes appreciably longer.
RBAC_PROPAGATION_TIMEOUT: Final[float] = 30.0
PROPAGATION_INTERVAL: Final[float] = 1.0


def unique_ident(prefix: str) -> str:
    """A unique key safe to embed in a condition expression.

    Same purpose as unique_key(), but underscore-separated: condition sets are
    compiled into policy where the key becomes part of an identifier, and a
    dash there is not worth the risk.
    """
    return unique_key(prefix).replace("-", "_")


async def wait_until(
    condition: Callable[[], Awaitable[bool]],
    description: str,
    timeout: float,
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


async def cleanup_step(action: Callable[[], Awaitable[Any]], description: str) -> None:
    """Run one teardown step, tolerating an object that is already gone."""
    try:
        await action()
    except PermitApiError as error:
        handle_cleanup_error(error, f"Got API Error during cleanup of {description}")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error during cleanup of {description}: {error}")
        pytest.fail(f"Got error during cleanup of {description}: {error}")


async def assert_gone(get: Callable[[str], Awaitable[Any]], key: str, description: str) -> None:
    """Assert the object this test created is really gone after teardown."""
    with pytest.raises(PermitApiError) as exc_info:
        await get(key)
    assert exc_info.value.status_code == 404, f"{description} '{key}' still exists after cleanup"


async def test_abac_e2e(permit: Permit):
    logger.info("initial setup of objects")
    # Every key is unique to this run: the e2e suite shares a single environment,
    # so fixed keys ("document", "admin", "viewer", "tesla") are objects other
    # tests create and delete underneath this one.
    resource_key = unique_ident("document")
    age_attribute = unique_ident("age")
    admin = RoleCreate(
        key=unique_ident("admin"),
        name="Admin",
        permissions=[f"{resource_key}:create", f"{resource_key}:read"],
    )
    viewer = RoleCreate(key=unique_ident("viewer"), name="Viewer", permissions=[f"{resource_key}:read"])
    tesla = TenantCreate(key=unique_ident("tesla"), name="Tesla Inc")
    user_a = UserCreate(
        key=unique_ident("asaf"),
        email="asaf@permit.io",
        first_name="Asaf",
        last_name="Cohen",
        attributes={age_attribute: 35},
    )
    user_b = UserCreate(
        key=unique_ident("john"),
        email="john@permit.io",
        first_name="John",
        last_name="Doe",
        attributes={age_attribute: 27},
    )
    user_c = UserCreate(
        key=unique_ident("jane"),
        email="jane@permit.io",
        first_name="Jane",
        last_name="Doe",
        attributes={age_attribute: 25},
    )
    users_over_thirty = ConditionSetCreate(
        key=unique_ident("users_over_thirty"),
        type=ConditionSetType.userset,
        name="Users over 30",
        conditions={"allOf": [{"allOf": [{f"user.{age_attribute}": {"greater-than": 30}}]}]},
    )
    private_docs = ConditionSetCreate(
        key=unique_ident("private_docs"),
        type=ConditionSetType.resourceset,
        resource_id=None,
        name="Private docs",
        conditions={"allOf": [{"allOf": [{"resource.private": {"equals": False}}]}]},
    )
    condition_sets = [users_over_thirty, private_docs]
    created_users = [user_a, user_b, user_c]
    created_tenants = [tesla]
    created_roles = [admin, viewer]
    sign_permission = f"{resource_key}:sign"
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

        private_docs.resource_id = document.id.hex

        assert document.key == resource_key
        assert document.name == "Document"
        assert document.description == "google drive document"
        assert document.urn == f"prn:gdrive:{resource_key}"
        assert len(document.actions or {}) == 5
        assert (document.actions or {}).get("create") is not None
        assert (document.actions or {}).get("read") is not None
        assert (document.actions or {}).get("update") is not None
        assert (document.actions or {}).get("delete") is not None
        assert (document.actions or {}).get("sign") is not None

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

        # create the user attribute this test's condition set reads
        await permit.api.resource_attributes.create(
            "__user", ResourceAttributeCreate(key=age_attribute, type=AttributeType.number)
        )

        # create tenants
        for tenant_data in created_tenants:
            tenant = await permit.api.tenants.create(tenant_data)
            assert tenant is not None
            assert tenant.key == tenant_data.key
            assert tenant.name == tenant_data.name
            assert tenant.description is None

        # create users
        for user_data in created_users:
            user = await permit.api.users.sync(user_data)
            assert user is not None
            assert user.key == user_data.key
            assert user.email == user_data.email
            assert user.first_name == user_data.first_name
            assert user.last_name == user_data.last_name
            assert set(user.attributes.keys()) == set(user_data.attributes.keys())

        # create role
        for role_data in created_roles:
            await permit.api.roles.create(role_data)

        # assign role to user in tenant
        await permit.api.users.assign_role(
            {
                "user": user_a.key,
                "role": admin.key,
                "tenant": tesla.key,
            }
        )

        await permit.api.users.assign_role(
            {
                "user": user_b.key,
                "role": admin.key,
                "tenant": tesla.key,
            }
        )

        logger.info("waiting for the role assignments to propagate to the PDP")

        # testing Admin permissions
        logger.info("testing admin permissions")
        await wait_until(
            lambda: permit.check(user_a.key, "create", {"type": resource_key, "tenant": tesla.key}),
            f"user '{user_a.key}' to be allowed to create '{resource_key}'",
            timeout=RBAC_PROPAGATION_TIMEOUT,
        )
        await wait_until(
            lambda: permit.check(user_b.key, "create", {"type": resource_key, "tenant": tesla.key}),
            f"user '{user_b.key}' to be allowed to create '{resource_key}'",
            timeout=RBAC_PROPAGATION_TIMEOUT,
        )

        assert not await permit.check(
            user_a.key,
            "sign",
            {"type": resource_key, "tenant": tesla.key},
        )
        assert not await permit.check(
            user_b.key,
            "sign",
            {"type": resource_key, "tenant": tesla.key},
        )

        print_break()

        logger.info("testing admin permissions in bulk")
        assert await permit.bulk_check(
            [
                {
                    "user": user_a.key,
                    "action": "create",
                    "resource": {"type": resource_key, "tenant": tesla.key},
                },
                {
                    "user": user_b.key,
                    "action": "create",
                    "resource": {"type": resource_key, "tenant": tesla.key},
                },
                {
                    "user": user_a.key,
                    "action": "sign",
                    "resource": {"type": resource_key, "tenant": tesla.key},
                },
                {
                    "user": user_b.key,
                    "action": "sign",
                    "resource": {"type": resource_key, "tenant": tesla.key},
                },
            ]
        ) == [True, True, False, False]

        print_break()

        logger.info("creating condition sets")
        for condition_set_data in condition_sets:
            condition_set = await permit.api.condition_sets.create(condition_set_data)
            assert condition_set.key == condition_set_data.key
            assert condition_set.type == condition_set_data.type

        # both condition sets this test created are listed
        for condition_set_data in condition_sets:
            listed_set = await find_by_key(
                lambda page: permit.api.condition_sets.list(page=page, per_page=PER_PAGE),
                condition_set_data.key,
            )
            assert listed_set is not None, f"condition set '{condition_set_data.key}' is missing from the list"
            assert listed_set.type == condition_set_data.type

        await permit.api.condition_set_rules.create(
            ConditionSetRuleCreate(
                user_set=users_over_thirty.key,
                permission=sign_permission,
                resource_set=private_docs.key,
            )
        )

        # scoped to this test's condition sets: the environment is shared, so
        # the unfiltered list contains every other test's rules too. The
        # permission is asserted on the result rather than passed as a filter:
        # the API matches the permission filter against the action key, not
        # against "<resource>:<action>" as ConditionSetRulesApi.list documents.
        rules = await permit.api.condition_set_rules.list(
            user_set_key=users_over_thirty.key,
            resource_set_key=private_docs.key,
        )
        assert len(rules) == 1
        assert rules[0].user_set == users_over_thirty.key
        assert rules[0].resource_set == private_docs.key
        assert rules[0].permission == sign_permission

        print_break()

        # Everything above is asserted for real against the control plane, and
        # the teardown below still runs. The decision assertions are pending
        # PER-16209. Skipped rather than xfailed so it reports honestly instead
        # of looking covered. pytest.Skipped derives from BaseException, so it
        # escapes the `except Exception` below and the `finally` teardown runs.
        pytest.skip("ABAC decision assertions are pending PER-16209; " "the control-plane assertions above still run.")

    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        # cleanup: each object is torn down on its own, so one already-gone
        # object does not leak the rest into the shared environment.
        await cleanup_step(
            lambda: permit.api.condition_set_rules.delete(
                ConditionSetRuleRemove(
                    user_set=users_over_thirty.key,
                    permission=sign_permission,
                    resource_set=private_docs.key,
                )
            ),
            "condition set rule",
        )
        for role in created_roles:
            await cleanup_step(lambda key=role.key: permit.api.roles.delete(key), f"role '{role.key}'")
        for user in created_users:
            await cleanup_step(lambda key=user.key: permit.api.users.delete(key), f"user '{user.key}'")
        for tenant_data in created_tenants:
            await cleanup_step(
                lambda key=tenant_data.key: permit.api.tenants.delete(key), f"tenant '{tenant_data.key}'"
            )
        for condition_set_data in condition_sets:
            await cleanup_step(
                lambda key=condition_set_data.key: permit.api.condition_sets.delete(key),
                f"condition set '{condition_set_data.key}'",
            )
        await cleanup_step(lambda: permit.api.resources.delete(resource_key), f"resource '{resource_key}'")
        await cleanup_step(
            lambda: permit.api.resource_attributes.delete("__user", age_attribute),
            f"user attribute '{age_attribute}'",
        )
        for role in created_roles:
            await assert_gone(permit.api.roles.get, role.key, "role")
        for user in created_users:
            await assert_gone(permit.api.users.get, user.key, "user")
        for tenant_data in created_tenants:
            await assert_gone(permit.api.tenants.get, tenant_data.key, "tenant")
        for condition_set_data in condition_sets:
            await assert_gone(permit.api.condition_sets.get, condition_set_data.key, "condition set")
        await assert_gone(permit.api.resources.get, resource_key, "resource")
