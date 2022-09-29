import pytest

from permit.api.client import PermitApiClient
from permit.config import ConfigFactory, PermitConfig


@pytest.fixture
def config() -> PermitConfig:
    return ConfigFactory.build(
        dict(
            token="permit_key_PLpDpaOpR4UAEbGbAgi76nyc6Z0EnFjFFdPW0oFFDov4XfONqHiJcx1kKfA7Fptjam9F9dUal9HoJnw7MJE7Ge",
            api_url="http://localhost:8000",
        ),
    )


@pytest.fixture
def api_client(config: PermitConfig) -> PermitApiClient:
    return PermitApiClient(config=config)
