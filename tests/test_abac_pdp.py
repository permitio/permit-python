import pytest

from permit import Permit, PermitConnectionError, TenantCreate, UserCreate


def abac_user(user: UserCreate):
    return user.dict(exclude={"first_name", "last_name"})


async def test_abac_pdp_cloud_error(permit_cloud: Permit):

    user_test = UserCreate(
        **dict(
            key="maya@permit.io",
            email="maya@permit.io",
            first_name="Maya",
            last_name="Barak",
            attributes={"age": 23},
        )
    )
    TESLA = TenantCreate(key="tesla", name="Tesla Inc")

    try:
        await permit_cloud.check(
            abac_user(user_test),
            "sign",
            {
                "type": "document",
                "tenant": TESLA.key,
                "attributes": {"private": False},
            },
        )

    except Exception as error:
        assert isinstance(error, PermitConnectionError)

    else:
        pytest.fail("Should have raised an exception")
