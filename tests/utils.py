import uuid

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


def handle_cleanup_error(error: PermitApiError, message: str):
    """Report a teardown failure without failing an otherwise-passing test.

    A 404 during cleanup means the object is already gone, which is the state
    teardown was trying to reach. Failing the test for it turns every ordering
    difference between tests that share an environment into a red build, and
    hides whatever the test was actually asserting.

    Anything other than a 404 still fails: that is a real teardown problem and
    it leaks objects into the shared environment.
    """
    if error.status_code == 404:
        logger.warning(f"{message}: already absent (404), continuing. url={error.request_url}")
        return
    handle_api_error(error, message)


def unique_key(prefix: str) -> str:
    """A key no concurrently-running test can collide with.

    The end-to-end tests all run against one environment, so any fixed key
    (``admin``, ``viewer``, ``document``) is shared mutable state: whichever
    test tears it down first breaks the others. Callers should derive every
    object key they create from this.
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
