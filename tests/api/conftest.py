import pytest

from permit.api.client import PermitApiClient
from permit.config import ConfigFactory, PermitConfig


@pytest.fixture
def config() -> PermitConfig:
    return ConfigFactory.build(
        dict(
            token="permit_key_UDpCznMpZqAeZzcW9gC3qhjwSHammpiuqiRJwleEWcMBcwcQHYB9vBHlBfgqxO41rXbtBiI7HBQPqxoaH3OXi5",
            api_url="http://localhost:8000"
        ),
    )


@pytest.fixture
def api_client(config: PermitConfig) -> PermitApiClient:
    return PermitApiClient(config=config)
