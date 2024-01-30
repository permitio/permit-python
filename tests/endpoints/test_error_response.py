import pytest
from loguru import logger

from permit import Permit
from permit.exceptions import PermitApiError, PermitConnectionError


async def test_api_error(permit: Permit):
    try:
        await permit.api.users.get("this_key_does_not_exists")
    except PermitApiError as error:
        err = f"Got error: status={error.status_code}, url={error.request_url}, method={error.response.method}, details={error.details}, content-type={error.content_type}"
        logger.info(err)
        assert error.content_type == "application/json"
    except PermitConnectionError as error:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
