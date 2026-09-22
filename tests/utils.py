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


# Statuses that mean "teardown did not leave a mess, and retrying here would
# not help either".
#   404 - the object is already gone, which is the state teardown wanted.
#   429 - the API throttled us. The whole suite runs in one environment and
#         tears a lot down at the end, so cleanup is exactly where the rate
#         limit bites. It leaks an object, which the scratch environment's
#         deletion reclaims anyway.
_CLEANUP_TOLERATED_STATUSES = frozenset({404, 429})


def handle_cleanup_error(error: PermitApiError, message: str):
    """Report a teardown failure without failing an otherwise-passing test.

    Failing a test for a teardown hiccup hides whatever it was actually
    asserting, and makes every ordering difference or rate-limit spike look
    like a product defect. Tolerated statuses are logged loudly and skipped.

    Every other status still fails the test: that is a real teardown problem.
    """
    if error.status_code in _CLEANUP_TOLERATED_STATUSES:
        logger.warning(
            f"{message}: tolerated during cleanup (status={error.status_code}), continuing. " f"url={error.request_url}"
        )
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
