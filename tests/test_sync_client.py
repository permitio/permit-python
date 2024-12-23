import random
from concurrent.futures.thread import ThreadPoolExecutor

import pytest

from permit import PermitConfig, UserCreate
from permit.sync import Permit


@pytest.fixture()
def permit(permit_config: PermitConfig) -> Permit:
    return Permit(permit_config)


def test_sync_client(permit: Permit):
    user_key = f"user-{random.randint(0, 1000)}"
    permit.api.users.create(
        UserCreate(
            key=user_key,
            email="test@example.com",
        )
    )
    user = permit.api.users.get(user_key)
    assert user.key == user_key
    permit.api.users.delete(user_key)


def test_sync_client_multithreading(permit_config: PermitConfig):
    instances = [Permit(permit_config) for _ in range(10)]

    with ThreadPoolExecutor() as executor:
        for instance in instances:
            executor.submit(test_sync_client, instance)
