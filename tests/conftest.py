import os

import pytest

from permit import Permit, PermitConfig
from permit.sync import Permit as SyncPermit


@pytest.fixture
def permit_config() -> PermitConfig:
    default_pdp_address = (
        "https://cloudpdp.api.permit.io"
        if os.getenv("CLOUD_PDP") == "true"
        else "http://localhost:7766"
    )
    default_api_address = (
        "https://api.permit.io"
        if os.getenv("API_TIER") == "prod"
        else "http://localhost:8000"
    )

    token = os.getenv("PDP_API_KEY", "")
    pdp_address = os.getenv("PDP_URL", default_pdp_address)
    api_url = os.getenv("PDP_CONTROL_PLANE", default_api_address)

    if not token:
        pytest.fail("PDP_API_KEY is not configured, test cannot run!")

    return PermitConfig(
        **{
            "token": token,
            "pdp": pdp_address,
            "api_url": api_url,
            "log": {
                "level": "debug",
                "enable": True,
            },
        }
    )


@pytest.fixture
def permit(permit_config: PermitConfig) -> Permit:
    return Permit(permit_config)


@pytest.fixture
def sync_permit(permit_config: PermitConfig) -> SyncPermit:
    return SyncPermit(permit_config)
