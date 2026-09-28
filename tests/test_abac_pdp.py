import os
from typing import Any, Dict, List

import aiohttp
import pytest

from permit import Permit, PermitConnectionError, TenantCreate, UserCreate

CLOUD_PDP_URL = "https://cloudpdp.api.permit.io"

# Every test in this module asserts what the CLOUD PDP does with a policy kind
# it does not implement: it answers 501 and the SDK turns that into
# PermitConnectionError. A full PDP container answers those same calls
# successfully, so the assertions are false there -- the tests are not merely
# slow or flaky off the cloud PDP, they are inapplicable.
#
# conftest's `permit_cloud` fixture resolves its address as
# os.getenv("PDP_URL", CLOUD_PDP_URL), so it only reaches the cloud PDP when
# PDP_URL is unset or already points there. CI sets PDP_URL to the local PDP
# sidecar (.github/workflows/test.yml), which means `permit_cloud` is a local
# PDP client there and these three tests cannot pass as written. Skipping on
# the same condition the fixture uses keeps them honest: they run where they
# are meaningful and are reported as skipped, with the reason, where they are
# not.
CONFIGURED_PDP_URL = os.getenv("PDP_URL", CLOUD_PDP_URL)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not CONFIGURED_PDP_URL.startswith(CLOUD_PDP_URL),
        reason=(
            f"cloud-PDP-only test: permit_cloud is configured against {CONFIGURED_PDP_URL}, "
            f"not {CLOUD_PDP_URL}. Unset PDP_URL (or point it at the cloud PDP) to run these."
        ),
    ),
]


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
