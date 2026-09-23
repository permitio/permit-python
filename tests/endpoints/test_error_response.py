import pytest
from loguru import logger

from permit import Permit
from permit.exceptions import PermitApiError


async def test_api_error(permit: Permit) -> None:
    with pytest.raises(PermitApiError) as exc_info:
        await permit.api.users.get("this_key_does_not_exists")
    error = exc_info.value
    logger.info(
        f"Got error: status={error.status_code}, url={error.request_url}, "
        f"method={error.response.method}, "
        f"details={error.details}, content-type={error.content_type}"
    )
    assert error.content_type == "application/json"
