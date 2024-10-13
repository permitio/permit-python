import pytest
from loguru import logger

from permit.exceptions import PermitApiError


def handle_api_error(error: PermitApiError, message: str):
    err = (
        f"{message}: status={error.status_code}, url={error.request_url}, method={error.response.method}, "
        f"details={error.details}, content-type={error.content_type}"
    )
    logger.error(err)
    pytest.fail(err)
