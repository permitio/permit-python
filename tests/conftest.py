import os

import pytest

from permit import Permit, PermitConfig


@pytest.fixture
def permit() -> Permit:
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

    config = PermitConfig(
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

    return Permit(config)
