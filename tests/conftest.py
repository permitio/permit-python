import asyncio
import functools
import os
import random
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from typing import Any, TypeVar

import pytest
from loguru import logger
from typing_extensions import ParamSpec

from permit import Permit, PermitConfig
from permit.api.base import SimpleHttpClient
from permit.exceptions import PermitApiError
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

P = ParamSpec("P")
R = TypeVar("R")


@pytest.fixture(scope="session")
def httpserver_listen_address() -> tuple[str, int]:
    return "localhost", MOCKED_PORT


@pytest.fixture
def permit_config() -> PermitConfig:
    default_pdp_address = (
        "https://cloudpdp.api.permit.io"
        if os.getenv("CLOUD_PDP") == "true"
        else "http://localhost:7766"
    )
    default_api_address = (
        "https://api.permit.io" if os.getenv("API_TIER") == "prod" else "http://localhost:8000"
    )

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


# --------------------------------------------------------------------------
# Rate-limit resilience
#
# The whole suite runs against ONE environment on the shared cloud test
# project, and it creates and tears down a lot. That exceeds the API's burst
# limit, which surfaces as HTTP 429 part-way through a test or during its
# teardown -- a throttled request, not a product defect.
#
# Previously eight of these tests were @pytest.mark.xfail, so their 429s were
# swallowed and nobody noticed. With the markers removed the throttling is
# visible, so it has to be handled honestly: retry with backoff until the call
# actually succeeds, rather than tolerating the failure. Tolerating is worse
# than it looks -- a tolerated DELETE leaves the object alive, and the
# assert-it-is-gone check that follows then fails with "DID NOT RAISE".
#
# This wraps the SDK's HTTP layer for the TEST SESSION ONLY. The SDK itself is
# unchanged: adding implicit retries to a published client is a behaviour
# change callers did not ask for.
# --------------------------------------------------------------------------

_RATE_LIMIT_STATUS = 429
# Six attempts (~63s of backoff) was not always enough: a teardown still
# exhausted them. Nine caps a single call at ~two minutes of waiting, which is
# cheap next to a red build, and the loop exits the moment the call succeeds.
_MAX_RETRIES = 9
_BASE_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 30.0


def _retry_after_seconds(err: PermitApiError) -> float | None:
    """The server's own Retry-After, when it sends one."""
    try:
        raw = err.response.headers.get("Retry-After")
    except Exception:  # a missing/odd header must never mask the 429
        return None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _retry_on_rate_limit(
    method: Callable[P, Awaitable[R]],
) -> Callable[P, Coroutine[Any, Any, R]]:
    @functools.wraps(method)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for attempt in range(_MAX_RETRIES):
            try:
                return await method(*args, **kwargs)
            except PermitApiError as err:
                if err.status_code != _RATE_LIMIT_STATUS or attempt == _MAX_RETRIES - 1:
                    raise
                # Prefer what the server asked for; otherwise exponential
                # backoff with jitter, so parallel callers do not retry in
                # lockstep and re-trip the limit together.
                delay = _retry_after_seconds(err)
                if delay is None:
                    delay = min(_BASE_BACKOFF_S * (2**attempt), _MAX_BACKOFF_S)
                    delay *= 0.5 + random.random() / 2  # noqa: S311 - jitter, not crypto
                logger.warning(
                    f"rate limited (429); retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
        msg = "unreachable"
        raise AssertionError(msg)  # pragma: no cover

    return wrapper


@pytest.fixture(scope="session", autouse=True)
def retry_rate_limited_requests() -> Iterator[None]:
    """Make every SDK HTTP verb retry a 429 for the duration of the test session."""
    verbs = ("get", "post", "put", "patch", "delete")
    originals = {verb: getattr(SimpleHttpClient, verb) for verb in verbs}
    for verb, original in originals.items():
        setattr(SimpleHttpClient, verb, _retry_on_rate_limit(original))
    yield
    for verb, original in originals.items():
        setattr(SimpleHttpClient, verb, original)
