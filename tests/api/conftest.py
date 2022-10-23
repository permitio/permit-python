import pytest

from permit.api.client import PermitApiClient
from permit.api.client_sync import PermitSyncApiClient
from permit.config import ConfigFactory, PermitConfig


@pytest.fixture
def config() -> PermitConfig:
    return ConfigFactory.build(
        dict(
            # dummy local api key for local tests
            token="permit_key_j6vbONQJMNJkH95LaueD6EzLjbiZ8uIaXtYtLXBPy1fdRUq2rjEd5lMQXGQ0SJDFZZEbL6Ftb7OvXD0UTmlOWU",
            api_url="http://localhost:8000",
        ),
    )


@pytest.fixture
def api_client(config: PermitConfig) -> PermitApiClient:
    return PermitApiClient(config=config)


@pytest.fixture
def sync_api_client(config: PermitConfig) -> PermitSyncApiClient:
    return PermitSyncApiClient(config=config)
