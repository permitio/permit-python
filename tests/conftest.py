import os

import pytest

from permit import Permit, PermitConfig
from permit.sync import Permit as SyncPermit

# pytest_httpserver's `httpserver` fixture is SESSION-scoped: the first test
# that asks for it binds the one shared server for the whole run. This address
# override therefore has to live in conftest.py, not in an individual test
# module -- a module-local override only applies if that module happens to be
# the first to touch the fixture, which makes the port silently depend on
# collection order.
#
# test_rbac_e2e.py's timeout tests connect to a hardcoded localhost:9999, so if
# any other module claims the server first the server binds elsewhere and those
# tests fail with "Cannot connect to host localhost:9999".
MOCKED_PORT = 9999


@pytest.fixture(scope="session")
def httpserver_listen_address() -> tuple:
    return "localhost", MOCKED_PORT


@pytest.fixture
def permit_config() -> PermitConfig:
    default_pdp_address = (
        "https://cloudpdp.api.permit.io" if os.getenv("CLOUD_PDP") == "true" else "http://localhost:7766"
    )
    default_api_address = "https://api.permit.io" if os.getenv("API_TIER") == "prod" else "http://localhost:8000"

    token = os.getenv("PDP_API_KEY", "")
    pdp_address = os.getenv("PDP_URL", default_pdp_address)
    api_url = os.getenv("PDP_CONTROL_PLANE", default_api_address)

    if not token:
        pytest.fail("PDP_API_KEY is not configured, test cannot run!")

    return PermitConfig(
        token=token,
        pdp=pdp_address,
        api_url=api_url,
        log={
            "level": "debug",
            "enable": True,
        },
    )


@pytest.fixture
def permit(permit_config: PermitConfig) -> Permit:
    return Permit(permit_config)


@pytest.fixture
def sync_permit(permit_config: PermitConfig) -> SyncPermit:
    return SyncPermit(permit_config)


@pytest.fixture
def permit_config_cloud() -> PermitConfig:
    token = os.getenv("PDP_API_KEY", "")
    pdp_address = os.getenv("PDP_URL", "https://cloudpdp.api.permit.io")
    api_url = os.getenv("PDP_CONTROL_PLANE", "https://api.permit.io")

    if not token:
        pytest.fail("PDP_API_KEY is not configured, test cannot run!")

    return PermitConfig(
        token=token,
        pdp=pdp_address,
        api_url=api_url,
        log={
            "level": "debug",
            "enable": True,
        },
    )


@pytest.fixture
def permit_cloud(permit_config_cloud: PermitConfig) -> Permit:
    return Permit(permit_config_cloud)
