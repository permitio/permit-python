import pytest
from aioresponses import aioresponses

from permit import Permit
from permit.sync import Permit as SyncPermit


@pytest.fixture
def client():
    return Permit("fake-token")


@pytest.fixture
def debug_client():
    return Permit("fake-token", debug_mode=True)


@pytest.fixture
def sync_client():
    return SyncPermit("fake-token")


@pytest.fixture
def debug_sync_client():
    return SyncPermit("fake-token", debug_mode=True)


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m
