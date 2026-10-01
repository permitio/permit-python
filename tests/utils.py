import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, TypeVar

import pytest
from loguru import logger
from werkzeug import Request

from permit.api.context import ApiContext
from permit.config import PermitConfig
from permit.exceptions import PermitApiError

# --- offline tests ------------------------------------------------------------
#
# The offline tests serve every request from a local pytest_httpserver, so they
# need no API key. offline_config() resolves the SDK's context to this project
# and environment up front, and the request paths below embed them.

ORG = "test-org"
PROJECT = "test-project"
ENVIRONMENT = "test-env"
FACTS = f"/v2/facts/{PROJECT}/{ENVIRONMENT}"
SCHEMA = f"/v2/schema/{PROJECT}/{ENVIRONMENT}"


def offline_config(base_url: str) -> PermitConfig:
    """Build a PermitConfig for an API and PDP at ``base_url``, its context already resolved.

    This is the state the SDK holds after a successful ``/v2/api-key/scope`` lookup, so no
    method under test needs to perform one.
    """
    api_context = ApiContext()
    api_context._save_api_key_accessible_scope(org=ORG, project=PROJECT, environment=ENVIRONMENT)
    api_context.set_environment_level_context(ORG, PROJECT, ENVIRONMENT)
    return PermitConfig(token="test-token", api_url=base_url, pdp=base_url, api_context=api_context)


class Call(NamedTuple):
    """A method, by the dotted path a user writes, and the arguments to call it with."""

    path: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


def call(path: str, *args: Any, **kwargs: Any) -> Call:
    return Call(path, args, kwargs)


def sent(request: Request) -> dict[str, Any]:
    """What a request put on the wire, in a form two requests can be compared by."""
    body = request.get_data()
    return {
        "method": request.method,
        "path": request.path,
        "query": sorted(request.args.items(multi=True)),
        "body": json.loads(body) if body else None,
    }


# --- end-to-end tests ---------------------------------------------------------

# The hosted cloud PDP. conftest.py's fixtures can default to it, and the e2e tests that
# run only on it, or never on it, compare the PDP address they are given with it.
CLOUD_PDP_URL = "https://cloudpdp.api.permit.io"


def handle_api_error(error: PermitApiError, message: str) -> None:
    err = (
        f"{message}: status={error.status_code}, url={error.request_url}, "
        f"method={error.response.method}, "
        f"details={error.details}, content-type={error.content_type}"
    )
    logger.error(err)
    pytest.fail(err)


# Only 404: the object is already gone, which is the state teardown wanted.
#
# 429 is deliberately NOT tolerated. Swallowing a throttled DELETE leaves the
# object alive, and the assert-it-is-gone check that follows then fails with
# "DID NOT RAISE" -- the tolerance manufactures a worse failure than the one it
# hides. Throttling is handled where it belongs, by the retry-with-backoff
# fixture in conftest.py, which makes the delete actually succeed.
_CLEANUP_TOLERATED_STATUSES = frozenset({404})


def handle_cleanup_error(error: PermitApiError, message: str) -> None:
    """Report a teardown failure without failing an otherwise-passing test.

    Failing a test for a teardown hiccup hides whatever it was actually
    asserting, and makes every ordering difference or rate-limit spike look
    like a product defect. Tolerated statuses are logged loudly and skipped.

    Every other status still fails the test: that is a real teardown problem.
    """
    if error.status_code in _CLEANUP_TOLERATED_STATUSES:
        logger.warning(
            f"{message}: tolerated during cleanup (status={error.status_code}), "
            f"continuing. url={error.request_url}"
        )
        return
    handle_api_error(error, message)


async def delete_quietly(delete: Callable[[], Awaitable[None]], description: str) -> None:
    """Delete one object at teardown. A 404 means it is already gone, which is the goal."""
    try:
        await delete()
    except PermitApiError as error:
        handle_cleanup_error(error, f"could not delete {description}")


def delete_quietly_blocking(delete: Callable[[], None], description: str) -> None:
    """Delete one object at teardown through the blocking client, as ``delete_quietly``."""
    try:
        delete()
    except PermitApiError as error:
        handle_cleanup_error(error, f"could not delete {description}")


T = TypeVar("T")


async def poll_for(
    fetch: Callable[[], Awaitable[T]], expected: T, *, timeout: float, interval: float
) -> T:
    """Poll ``fetch`` every ``interval`` seconds until it returns ``expected``.

    It stops after ``timeout`` seconds. The last answer is returned either way, so the
    caller's assertion reports the value it got.
    """
    deadline = time.monotonic() + timeout
    answer = await fetch()
    while answer != expected and time.monotonic() < deadline:
        await asyncio.sleep(interval)
        answer = await fetch()
    return answer


def unique_key(prefix: str) -> str:
    """A key no concurrently-running test can collide with.

    The end-to-end tests all run against one environment, so any fixed key
    (``admin``, ``viewer``, ``document``) is shared mutable state: whichever
    test tears it down first breaks the others. Callers should derive every
    object key they create from this.
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
