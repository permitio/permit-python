from typing import Any, Dict, List

import aiohttp
import pytest

from permit import Permit, PermitConnectionError, TenantCreate, UserCreate


def abac_user(user: UserCreate):
    return user.dict(exclude={"first_name", "last_name"})


async def test_abac_pdp_cloud_error(permit_cloud: Permit):
    user_test = UserCreate(
        key="maya@permit.io",
        email="maya@permit.io",
        first_name="Maya",
        last_name="Barak",
        attributes={"age": 23},
    )
    tesla = TenantCreate(key="tesla", name="Tesla Inc")

    try:
        await permit_cloud.check(
            abac_user(user_test),
            "sign",
            {
                "type": "document",
                "tenant": tesla.key,
                "attributes": {"private": False},
            },
        )
    except (PermitConnectionError, aiohttp.ClientError) as error:
        assert isinstance(error, PermitConnectionError)
    else:
        pytest.fail("Should have raised an exception")


async def test_get_user_permissions_cloud_error(permit_cloud: Permit):
    user_test = UserCreate(
        key="maya@permit.io",
        email="maya@permit.io",
        first_name="Maya",
        last_name="Barak",
        attributes={"age": 23},
    )

    try:
        await permit_cloud.get_user_permissions(
            user={"key": user_test.key, "email": user_test.email, "attributes": user_test.attributes},
            tenants=["default"],
            resources=["Blog:dddddd"],
            resource_types=["Blog"],
        )
    except (PermitConnectionError, aiohttp.ClientError) as error:
        assert isinstance(error, PermitConnectionError)
    else:
        pytest.fail("Should have raised an exception")


async def test_filter_objects_cloud_error(permit_cloud: Permit):
    user_test = {"key": "maya@permit.io", "email": "maya@permit.io", "attributes": {"age": 23}}

    test_resources: List[Dict[str, Any]] = [
        {"type": "Blog", "key": "doc1", "context": {}, "attributes": {}, "tenant": "default"},
        {"type": "Document", "key": "doc2", "context": {}, "attributes": {}, "tenant": "default"},
    ]

    try:
        await permit_cloud.filter_objects(user=user_test, action="read", context={}, resources=test_resources)
    except (PermitConnectionError, aiohttp.ClientError) as error:
        assert isinstance(error, PermitConnectionError)
    else:
        pytest.fail("Should have raised an exception")
