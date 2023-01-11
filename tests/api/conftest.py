import pytest

from permit.api.client import PermitApiClient
from permit.api.client_sync import PermitSyncApiClient
from permit.config import ConfigFactory, PermitConfig, PermitContext
from tests.api.consts import MOCK_API_URL


@pytest.fixture
def config() -> PermitConfig:
    mock_context = PermitContext(project="testing-mock", environment="test")
    return ConfigFactory.build(
        dict(
            # dummy local api key for local tests
            token="permit_key_j6vbONQJMNJkH95LaueD6EzLjbiZ8uIaXtYtLXBPy1fdRUq2rjEd5lMQXGQ0SJDFZZEbL6Ftb7OvXD0UTmlOWU",
            api_url=MOCK_API_URL,
            context=mock_context
        ),
    )


@pytest.fixture
async def api_client(config: PermitConfig) -> PermitApiClient:
    api_client = PermitApiClient(config=config)
    return api_client


@pytest.fixture
def sync_api_client(config: PermitConfig) -> PermitSyncApiClient:
    return PermitSyncApiClient(config=config)
