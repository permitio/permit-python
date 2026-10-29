"""Offline tests for the SDK's logging (PER-16680).

The SDK logs through loguru's process-wide logger and adds no sink of its own. These tests
add sinks the way an application does, and read what reached them: a text sink on stderr in
loguru's default format, read through capsys, and a serialized (JSON) sink. Every request is
served by a local pytest_httpserver.
"""

import dataclasses
import inspect
import json
import pprint
import re
import socketserver
import subprocess
import sys
import threading
import traceback
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn, cast

import aiohttp
import pytest
from loguru import logger
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

import permit.logger as permit_logger
from permit import Permit, PermitConfig
from permit.enforcement.enforcer import CheckQuery
from permit.exceptions import PermitApiError, PermitConnectionError, scrub_request_info
from permit.sync import Permit as SyncPermit
from permit.utils.sdk_logger import REDACTED, SdkLogger, sdk_logger, without_userinfo

SENTINEL = "permit_key_SENTINEL_9f8e7d6c5b4a39281706f5e4d3c2b1a0"
# The key as given and as aiohttp lower-cases it in some of its error messages.
SENTINEL_SPELLINGS = (SENTINEL, SENTINEL.lower())
ORG_ID = "00000000-0000-4000-8000-00000000000a"
PROJECT_ID = "00000000-0000-4000-8000-00000000000b"
ENV_ID = "00000000-0000-4000-8000-00000000000c"
USERS = f"/v2/facts/{PROJECT_ID}/{ENV_ID}/users"
WAIT_FOR_SYNC_WARNING = "Tried to wait for synced facts"


def _probe() -> None:
    logger.log("TRACE", "permit logging probe")


def _permit_records_enabled() -> bool:
    """Whether loguru lets the records of the permit package through right now.

    loguru has no getter for this, so log a TRACE record from a function whose module name
    is in the package, and see whether a sink receives it.
    """
    received: list[str] = []
    probe_module = "permit._logging_probe"
    sink_id = logger.add(
        received.append, level="TRACE", filter=lambda record: record["name"] == probe_module
    )
    try:
        types.FunctionType(_probe.__code__, {"__name__": probe_module, "logger": logger})()
    finally:
        logger.remove(sink_id)
    return bool(received)


@pytest.fixture(autouse=True)
def isolated_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start as a fresh process does, and put the SdkLogger and loguru's switches back after.

    Restoring loguru's switch for "permit" also drops any switch a test set for a module of
    the package.
    """
    monkeypatch.setattr(permit_logger, "_warned_levels", set())
    was_enabled = _permit_records_enabled()
    saved = vars(sdk_logger).copy()
    vars(sdk_logger).update(vars(SdkLogger()))
    logger.enable("permit")
    yield
    vars(sdk_logger).update(saved)
    if was_enabled:
        logger.enable("permit")
    else:
        logger.disable("permit")


@dataclass
class AppSinks:
    """What the application's own loguru sinks received during a test."""

    capsys: pytest.CaptureFixture[str]
    json_lines: list[str] = field(default_factory=list)
    _stderr: str = ""

    def stderr(self) -> str:
        captured = self.capsys.readouterr()
        assert captured.out == ""
        self._stderr += captured.err
        return self._stderr

    def everything(self) -> str:
        return self.stderr() + "".join(self.json_lines)

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line)["record"] for line in self.json_lines]

    def sdk_records(self) -> list[dict[str, Any]]:
        return [
            record
            for record in self.records()
            if record["name"] == "permit" or record["name"].startswith("permit.")
        ]

    def sdk_levels(self) -> set[str]:
        return {record["level"]["name"] for record in self.sdk_records()}

    def wait_for_sync_warnings(self) -> list[dict[str, Any]]:
        """The records of the warning `wait_for_sync` logs when facts are not proxied."""
        return [
            record for record in self.sdk_records() if WAIT_FOR_SYNC_WARNING in record["message"]
        ]


def write_to_stderr(message: str) -> None:
    """Write to the sys.stderr of the moment: capsys replaces it in each phase of a test."""
    sys.stderr.write(message)


@pytest.fixture
def app_sinks(capsys: pytest.CaptureFixture[str]) -> Iterator[AppSinks]:
    """A stderr sink in loguru's default format and a JSON sink, both at DEBUG."""
    sinks = AppSinks(capsys)
    sink_ids = [
        logger.add(write_to_stderr, level="DEBUG"),
        logger.add(sinks.json_lines.append, level="DEBUG", serialize=True),
    ]
    yield sinks
    for sink_id in sink_ids:
        logger.remove(sink_id)


def make_config(httpserver: HTTPServer, *, token: str = SENTINEL, **log: Any) -> PermitConfig:
    url = httpserver.url_for("").rstrip("/")
    return PermitConfig(token=token, api_url=url, pdp=url, log=log)


def serve(httpserver: HTTPServer) -> None:
    """Answer the requests `use_async_client` and `use_sync_client` make."""
    httpserver.expect_request("/v2/api-key/scope", method="GET").respond_with_json(
        {"organization_id": ORG_ID, "project_id": PROJECT_ID, "environment_id": ENV_ID}
    )
    httpserver.expect_request(USERS, method="GET").respond_with_json(
        {"data": [], "total_count": 0, "page_count": 0}
    )
    # Not JSON, so reading the response raises an aiohttp error, which the SDK logs.
    httpserver.expect_request(f"{USERS}/user-1", method="GET").respond_with_data(
        "not json", content_type="text/plain"
    )
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_data(
        "PDP failure", status=500
    )


BULK: list[CheckQuery] = [{"user": "user-1", "action": "read", "resource": "document"}]


async def use_async_client(permit: Permit) -> None:
    """Go through every kind of record the SDK logs: DEBUG, WARNING and ERROR."""
    with permit.wait_for_sync():
        pass
    assert await permit.check("user-1", "read", "document")
    await permit.api.users.list()
    with pytest.raises(PermitConnectionError):
        await permit.api.users.get("user-1")
    with pytest.raises(PermitConnectionError):
        await permit.bulk_check(BULK)


def use_sync_client(permit: SyncPermit) -> None:
    """The blocking twin of `use_async_client`."""
    with permit.wait_for_sync():
        pass
    assert permit.check("user-1", "read", "document")
    permit.api.users.list()
    with pytest.raises(PermitConnectionError):
        permit.api.users.get("user-1")
    with pytest.raises(PermitConnectionError):
        permit.bulk_check(BULK)


async def use_client(permit: Permit) -> None:
    """`use_async_client` or `use_sync_client`, whichever fits the client."""
    if isinstance(permit, SyncPermit):
        use_sync_client(permit)
    else:
        await use_async_client(permit)


async def resolved(result: object) -> object:
    """The value of an SDK call: awaited for the async client, as is for the blocking one."""
    return await result if inspect.isawaitable(result) else result


CLIENT_CLASSES = [pytest.param(Permit, id="async"), pytest.param(SyncPermit, id="sync")]


def assert_api_key_not_logged(
    httpserver: HTTPServer, app_sinks: AppSinks, expected_levels: set[str]
) -> None:
    # The key was in use: every request carried it.
    sent = {request.headers.get("Authorization") for request, _ in httpserver.log}
    assert sent == {f"Bearer {SENTINEL}"}
    output = app_sinks.everything()
    assert SENTINEL not in output
    # Nothing was redacted either: no SDK record held the key in the first place.
    assert REDACTED not in output
    assert app_sinks.sdk_levels() == expected_levels
    # Each SDK record is one line on stderr, in the sink's format.
    assert app_sinks.stderr().count(" | permit.") == len(app_sinks.sdk_records())


LOG_LEVELS = [
    pytest.param({"level": "debug"}, {"DEBUG", "WARNING", "ERROR"}, id="debug"),
    pytest.param({"level": "info"}, {"WARNING", "ERROR"}, id="info"),
    pytest.param({}, {"WARNING", "ERROR"}, id="unset"),
]
AS_JSON = [pytest.param(True, id="json"), pytest.param(False, id="text")]


@pytest.mark.parametrize(("log", "expected_levels"), LOG_LEVELS)
@pytest.mark.parametrize("as_json", AS_JSON)
async def test_async_client_never_logs_the_api_key(
    httpserver: HTTPServer,
    app_sinks: AppSinks,
    log: dict[str, str],
    expected_levels: set[str],
    *,
    as_json: bool,
) -> None:
    serve(httpserver)

    await use_async_client(Permit(make_config(httpserver, enable=True, json=as_json, **log)))

    assert_api_key_not_logged(httpserver, app_sinks, expected_levels)


@pytest.mark.parametrize(("log", "expected_levels"), LOG_LEVELS)
@pytest.mark.parametrize("as_json", AS_JSON)
def test_sync_client_never_logs_the_api_key(
    httpserver: HTTPServer,
    app_sinks: AppSinks,
    log: dict[str, str],
    expected_levels: set[str],
    *,
    as_json: bool,
) -> None:
    serve(httpserver)

    use_sync_client(SyncPermit(make_config(httpserver, enable=True, json=as_json, **log)))

    assert_api_key_not_logged(httpserver, app_sinks, expected_levels)


def echo_the_key(request: Request) -> Response:
    """A PDP that rejects the request and echoes the API key it was sent."""
    return Response(f"rejected key: {request.headers['Authorization']}", status=403)


@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
@pytest.mark.parametrize(
    ("log", "application_enables", "logs_the_error"),
    [
        pytest.param({"enable": True, "level": "trace"}, False, True, id="trace"),
        pytest.param({"enable": True, "level": "debug"}, False, True, id="debug"),
        pytest.param({"enable": True, "level": "info"}, False, True, id="info"),
        pytest.param({"enable": True, "level": "error"}, False, True, id="error"),
        pytest.param({"enable": True, "level": "critical"}, False, False, id="critical"),
        pytest.param({"enable": False}, False, False, id="disabled"),
        # A client created with logging disabled, whose records the application turns on.
        pytest.param({"enable": False}, True, True, id="disabled-application-enables"),
    ],
)
async def test_an_api_key_the_pdp_echoes_back_is_redacted(
    httpserver: HTTPServer,
    app_sinks: AppSinks,
    client_class: type[Permit],
    log: dict[str, Any],
    *,
    application_enables: bool,
    logs_the_error: bool,
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_handler(echo_the_key)
    permit = client_class(make_config(httpserver, **log))
    if application_enables:
        logger.enable("permit")

    with pytest.raises(PermitConnectionError) as raised:
        await resolved(permit.check("user-1", "read", "document"))

    errors = [record for record in app_sinks.sdk_records() if record["level"]["name"] == "ERROR"]
    if logs_the_error:
        [record] = errors
        assert f"rejected key: Bearer {REDACTED}" in record["message"]
    else:
        assert app_sinks.sdk_records() == []
    assert SENTINEL not in app_sinks.everything()
    # The application gets the body too, in the exception it may log or report.
    assert f"rejected key: Bearer {REDACTED}" in str(raised.value)
    assert SENTINEL not in str(raised.value)


async def test_errors_raised_for_a_pdp_that_echoes_the_key_do_not_hold_it(
    httpserver: HTTPServer,
) -> None:
    for path in ("/allowed", "/allowed/bulk", "/authorized_users"):
        httpserver.expect_request(path, method="POST").respond_with_handler(echo_the_key)
    permit = Permit(make_config(httpserver))
    sync_permit = SyncPermit(make_config(httpserver))

    raised: list[PermitConnectionError] = []
    for call in (
        lambda: permit.check("user-1", "read", "document"),
        lambda: permit.bulk_check(BULK),
        lambda: permit.authorized_users("read", "document"),
    ):
        with pytest.raises(PermitConnectionError) as error:
            await call()
        raised.append(error.value)
    with pytest.raises(PermitConnectionError) as error:
        sync_permit.check("user-1", "read", "document")
    raised.append(error.value)

    for error_value in raised:
        assert f"rejected key: Bearer {REDACTED}" in str(error_value)
        assert SENTINEL not in str(error_value)


async def test_a_key_is_redacted_whole_when_another_key_is_a_prefix_of_it(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    # Clients created earlier in the process with keys the real key starts with.
    for length in range(len("permit_key_"), len(SENTINEL), 2):
        Permit(make_config(httpserver, token=SENTINEL[:length], enable=True))
    httpserver.expect_request("/allowed", method="POST").respond_with_handler(echo_the_key)
    permit = Permit(make_config(httpserver, enable=True))

    with pytest.raises(PermitConnectionError):
        await permit.check("user-1", "read", "document")

    [record] = [record for record in app_sinks.sdk_records() if record["level"]["name"] == "ERROR"]
    assert record["message"].endswith(f"rejected key: Bearer {REDACTED}")
    assert SENTINEL[-8:] not in app_sinks.everything()


async def test_a_key_with_a_trailing_space_is_redacted_when_echoed_without_it(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_handler(echo_the_key)
    permit = Permit(make_config(httpserver, token=f"{SENTINEL} ", enable=True))

    with pytest.raises(PermitConnectionError):
        await permit.check("user-1", "read", "document")

    [record] = [record for record in app_sinks.sdk_records() if record["level"]["name"] == "ERROR"]
    assert record["message"].endswith(f"rejected key: Bearer {REDACTED}")
    assert SENTINEL not in app_sinks.everything()


@pytest.mark.parametrize(
    ("log", "expected_levels"),
    [
        pytest.param({"level": "trace"}, {"DEBUG", "WARNING", "ERROR"}, id="trace"),
        pytest.param({"level": "debug"}, {"DEBUG", "WARNING", "ERROR"}, id="debug"),
        pytest.param({}, {"WARNING", "ERROR"}, id="unset"),
        pytest.param({"level": "INFO"}, {"WARNING", "ERROR"}, id="INFO"),
        pytest.param({"level": "warning"}, {"WARNING", "ERROR"}, id="warning"),
        pytest.param({"level": "warn"}, {"WARNING", "ERROR"}, id="warn"),
        pytest.param({"level": "error"}, {"ERROR"}, id="error"),
        pytest.param({"level": "critical"}, set(), id="critical"),
        pytest.param({"level": "fatal"}, set(), id="fatal"),
    ],
)
@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
async def test_level_drops_the_sdk_records_below_it(
    httpserver: HTTPServer,
    app_sinks: AppSinks,
    client_class: type[Permit],
    log: dict[str, str],
    expected_levels: set[str],
) -> None:
    serve(httpserver)

    await use_client(client_class(make_config(httpserver, enable=True, **log)))
    logger.debug("an application record")

    assert app_sinks.sdk_levels() == expected_levels
    # Each name is one loguru knows, or reads as one: none falls back to INFO.
    assert [r for r in app_sinks.sdk_records() if "Unknown log level" in r["message"]] == []
    assert SENTINEL not in app_sinks.everything()
    # The application's own records are not the SDK's to filter.
    assert "an application record" in [record["message"] for record in app_sinks.records()]


# "²" is a digit to str.isdigit, but not a number int() reads.
@pytest.mark.parametrize("level", ["verbose", "²"])
async def test_an_unknown_level_warns_and_logs_at_info(
    httpserver: HTTPServer, app_sinks: AppSinks, level: str
) -> None:
    serve(httpserver)

    await use_async_client(Permit(make_config(httpserver, enable=True, level=level)))

    warnings = [
        record
        for record in app_sinks.sdk_records()
        if record["level"]["name"] == "WARNING"
        and f"Unknown log level {level!r}" in record["message"]
    ]
    assert len(warnings) == 1
    assert "logs at INFO" in warnings[0]["message"]
    # The same records as with level "info": no DEBUG ones.
    assert app_sinks.sdk_levels() == {"WARNING", "ERROR"}
    # The label applies on this path too.
    assert [r for r in app_sinks.sdk_records() if not r["message"].startswith("[Permit] ")] == []


def test_the_traceback_of_a_failed_client_creation_hides_the_api_key(
    httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_: object) -> None:
        msg = "the SDK could not configure its logger"
        raise RuntimeError(msg)

    monkeypatch.setattr("permit.logger.sdk_logger.enable", fail)
    lines: list[str] = []
    # diagnose=True, loguru's default, prints the value of each name on every line of the
    # traceback, and the SDK's frames pass the config around.
    sink_id = logger.add(lines.append, diagnose=True, backtrace=True)
    config = make_config(httpserver, enable=True)
    try:
        try:
            SyncPermit(config)
        except RuntimeError:
            logger.exception("the application could not start")
    finally:
        logger.remove(sink_id)

    output = "".join(lines)
    assert "configure_logger(" in output
    assert "PermitConfig(pdp=" in output
    assert SENTINEL not in output
    assert SENTINEL not in str(config)


# loguru cannot remove a level once added, so this application runs in its own process.
CUSTOM_LEVEL_APP = f"""
import sys

from loguru import logger

from permit import PermitConnectionError
from permit.sync import Permit

logger.remove()
logger.add(sys.stdout, serialize=True)
logger.level("audit", no=35)
url = sys.argv[1]
permit = Permit(
    token="{SENTINEL}", api_url=url, pdp=url, log={{"enable": True, "level": "audit"}}
)
with permit.wait_for_sync():
    pass
try:
    permit.check("user-1", "read", "document")
except PermitConnectionError:
    pass
"""


def test_level_accepts_a_level_the_application_added(
    httpserver: HTTPServer, tmp_path: Path
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_data(
        "PDP failure", status=500
    )
    app = tmp_path / "app.py"
    app.write_text(CUSTOM_LEVEL_APP)

    result = subprocess.run(
        [sys.executable, str(app), httpserver.url_for("").rstrip("/")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    # "audit" (35) sits between WARNING (30) and ERROR (40): only the ERROR record is kept.
    [record] = [json.loads(line)["record"] for line in result.stdout.splitlines()]
    assert record["level"]["name"] == "ERROR"
    assert record["message"].startswith("[Permit] error in permit.check(")
    assert SENTINEL not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("log", "prefix"),
    [
        pytest.param({}, "[Permit] ", id="default"),
        pytest.param({"label": "acme-authz"}, "[acme-authz] ", id="custom"),
    ],
)
async def test_label_prefixes_every_sdk_message(
    httpserver: HTTPServer, app_sinks: AppSinks, log: dict[str, str], prefix: str
) -> None:
    serve(httpserver)

    await use_async_client(Permit(make_config(httpserver, enable=True, level="debug", **log)))

    messages = [record["message"] for record in app_sinks.sdk_records()]
    assert len(messages) > 3
    assert [message for message in messages if not message.startswith(prefix)] == []
    assert f"{prefix}{WAIT_FOR_SYNC_WARNING}" in app_sinks.stderr()


def test_an_empty_label_adds_no_prefix(httpserver: HTTPServer, app_sinks: AppSinks) -> None:
    with SyncPermit(make_config(httpserver, enable=True, label="")).wait_for_sync():
        pass

    [record] = app_sinks.wait_for_sync_warnings()
    assert record["message"].startswith(WAIT_FOR_SYNC_WARNING)


@pytest.mark.parametrize("token", ["", " "])
def test_an_empty_api_key_redacts_nothing(
    httpserver: HTTPServer, app_sinks: AppSinks, token: str
) -> None:
    with SyncPermit(make_config(httpserver, token=token, enable=True)).wait_for_sync():
        pass

    [record] = app_sinks.wait_for_sync_warnings()
    assert (
        record["message"]
        == f"[Permit] {WAIT_FOR_SYNC_WARNING} but proxy_facts_via_pdp is disabled, ignoring..."
    )


def test_records_name_the_sdk_module_that_logged_them(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    with SyncPermit(make_config(httpserver, enable=True)).wait_for_sync():
        pass

    [record] = app_sinks.wait_for_sync_warnings()
    assert (record["name"], record["function"]) == ("permit.permit", "wait_for_sync")
    assert "| permit.permit:wait_for_sync:" in app_sinks.stderr()


@pytest.mark.parametrize("as_json", AS_JSON)
def test_log_as_json_leaves_the_format_to_the_application_sinks(
    httpserver: HTTPServer, app_sinks: AppSinks, *, as_json: bool
) -> None:
    with SyncPermit(make_config(httpserver, enable=True, json=as_json)).wait_for_sync():
        pass

    # One text line in the stderr sink and one JSON line in the JSON sink: the SDK
    # neither adds a JSON sink of its own nor changes the application's.
    [line] = [line for line in app_sinks.stderr().splitlines() if WAIT_FOR_SYNC_WARNING in line]
    assert "| WARNING  | permit.permit:wait_for_sync:" in line
    assert len(app_sinks.wait_for_sync_warnings()) == 1


DISABLED = [
    pytest.param({}, id="unset"),
    pytest.param({"enable": False}, id="false"),
    pytest.param(
        {"enable": False, "level": "debug", "label": "x", "json": True}, id="false-with-options"
    ),
    pytest.param({"enable": False, "level": "not-a-level"}, id="false-unknown-level"),
]


@pytest.mark.parametrize("log", DISABLED)
async def test_async_client_with_logging_disabled_logs_nothing(
    httpserver: HTTPServer, app_sinks: AppSinks, log: dict[str, Any]
) -> None:
    serve(httpserver)

    await use_async_client(Permit(make_config(httpserver, **log)))

    assert app_sinks.everything() == ""


@pytest.mark.parametrize("log", DISABLED)
def test_sync_client_with_logging_disabled_logs_nothing(
    httpserver: HTTPServer, app_sinks: AppSinks, log: dict[str, Any]
) -> None:
    serve(httpserver)

    use_sync_client(SyncPermit(make_config(httpserver, **log)))

    assert app_sinks.everything() == ""


def test_the_client_created_last_decides_whether_the_sdk_logs(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    SyncPermit(make_config(httpserver))
    enabled = SyncPermit(make_config(httpserver, enable=True))
    with enabled.wait_for_sync():
        pass
    assert len(app_sinks.wait_for_sync_warnings()) == 1

    SyncPermit(make_config(httpserver))
    with enabled.wait_for_sync():
        pass
    assert len(app_sinks.wait_for_sync_warnings()) == 1


def test_an_enabled_client_keeps_a_disable_the_application_set_for_an_sdk_module(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    logger.disable("permit.enforcement")

    permit = SyncPermit(make_config(httpserver, enable=True, level="debug"))
    assert permit.check("user-1", "read", "document")

    modules = {record["name"] for record in app_sinks.sdk_records()}
    assert "permit.permit" in modules
    assert [module for module in modules if module.startswith("permit.enforcement")] == []


def test_an_enabled_client_keeps_a_disable_the_application_set_for_the_sdk(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    logger.disable("permit")

    with SyncPermit(make_config(httpserver, enable=True)).wait_for_sync():
        pass

    assert app_sinks.sdk_records() == []


def proxied_config(httpserver: HTTPServer, **log: Any) -> PermitConfig:
    """A config that writes facts through the PDP, so `wait_for_sync` derives a client."""
    config = make_config(httpserver, **log)
    config.proxy_facts_via_pdp = True
    return config


def test_wait_for_sync_keeps_logging_off_after_a_disabled_client(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    proxied = SyncPermit(proxied_config(httpserver, enable=True))
    unproxied = SyncPermit(make_config(httpserver, enable=True))
    SyncPermit(make_config(httpserver))

    with proxied.wait_for_sync():
        pass
    with unproxied.wait_for_sync():
        pass

    assert app_sinks.sdk_records() == []


def test_wait_for_sync_keeps_the_level_and_label_of_the_client_created_last(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    proxied = SyncPermit(proxied_config(httpserver, enable=True, level="debug", label="first"))
    last = SyncPermit(make_config(httpserver, enable=True, level="warning", label="last"))
    records_before = len(app_sinks.sdk_records())

    with proxied.wait_for_sync():
        pass
    with last.wait_for_sync():
        pass

    [record] = app_sinks.sdk_records()[records_before:]
    assert record["message"].startswith(f"[last] {WAIT_FOR_SYNC_WARNING}")


@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
async def test_wait_for_sync_yields_a_client_that_waits_for_the_facts(
    httpserver: HTTPServer, client_class: type[Permit]
) -> None:
    serve(httpserver)
    httpserver.expect_request(re.compile(r"/facts/tenants/.*"), method="DELETE").respond_with_data(
        "", status=204
    )
    permit = client_class(proxied_config(httpserver))

    with permit.wait_for_sync(timeout=3.0, policy="fail") as waiting:
        assert type(waiting) is client_class
        assert waiting.config.facts_sync_timeout == 3.0
        deleted = waiting.api.tenants.delete("tenant-1")
        if client_class is Permit:
            await deleted
    deleted = permit.api.tenants.delete("tenant-2")
    if client_class is Permit:
        await deleted

    [waited, not_waited] = [
        request for request, _ in httpserver.log if request.path.startswith("/facts/")
    ]
    assert waited.path == "/facts/tenants/tenant-1"
    assert (waited.headers.get("X-Wait-Timeout"), waited.headers.get("X-Timeout-Policy")) == (
        "3.0",
        "fail",
    )
    assert "X-Wait-Timeout" not in not_waited.headers
    assert permit.config.facts_sync_timeout is None


def test_the_application_can_still_turn_the_sdk_records_on_itself(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    permit = SyncPermit(make_config(httpserver))

    logger.enable("permit")
    assert permit.check("user-1", "read", "document")

    # No client enabled logging, so no level or label applies: the records are as before.
    [record] = app_sinks.sdk_records()
    assert record["level"]["name"] == "DEBUG"
    assert record["message"].startswith("permit.check() response:")


def _next_handler_id() -> int:
    """The id loguru gives the next sink: each `logger.add` takes the next one."""
    sink_id = logger.add(lambda _: None)
    logger.remove(sink_id)
    return sink_id


def test_creating_many_clients_adds_no_sinks(httpserver: HTTPServer, app_sinks: AppSinks) -> None:
    first_free_id = _next_handler_id()

    clients = [
        client_class(make_config(httpserver, enable=True, json=True, label=f"client-{index}"))
        for index in range(20)
        for client_class in (Permit, SyncPermit)
    ]

    assert _next_handler_id() == first_free_id + 1
    with clients[-1].wait_for_sync():
        pass
    assert len(app_sinks.wait_for_sync_warnings()) == 1
    assert app_sinks.stderr().count(WAIT_FOR_SYNC_WARNING) == 1


def echo_the_key_as_json(request: Request) -> Response:
    """An API that rejects the request and echoes the key it was sent, in a JSON body."""
    body = {"detail": f"rejected key: {request.headers['Authorization']}", "error_code": "x"}
    return Response(json.dumps(body), status=403, content_type="application/json")


def json_escaped(text: str) -> str:
    r"""`text` as JSON may spell it in a string: every character a `\u` escape.

    The key then appears only once the body is decoded, not in its raw text.
    """
    return "".join(f"\\u{ord(char):04x}" for char in text)


def echo_the_key_in_a_list(request: Request) -> Response:
    """An API that rejects the request and echoes the key it was sent, in a list of errors."""
    key = json_escaped(request.headers["Authorization"])
    body = f'{{"detail": [{{"msg": "bad key {key}"}}]}}'
    return Response(body, status=422, content_type="application/json")


def redirect_to_user_2(_: Request) -> Response:
    """A redirect the client follows, with its headers, to the user-2 URL."""
    return Response(status=307, headers={"Location": f"{USERS}/user-2"})


@pytest.mark.parametrize(
    "handler",
    [echo_the_key, echo_the_key_as_json, echo_the_key_in_a_list],
    ids=["text", "json", "json-list"],
)
async def test_api_and_pdp_api_errors_do_not_hold_an_echoed_key(
    httpserver: HTTPServer, handler: Callable[[Request], Response]
) -> None:
    """The REST API and the PDP's local API raise through `handle_api_error`."""
    serve(httpserver)
    httpserver.expect_request(f"{USERS}/user-2", method="GET").respond_with_handler(handler)
    httpserver.expect_request(f"{USERS}/moved", method="GET").respond_with_handler(
        redirect_to_user_2
    )
    httpserver.expect_request("/local/role_assignments", method="GET").respond_with_handler(handler)
    permit = Permit(make_config(httpserver))

    raised: list[BaseException] = []
    for call in (
        permit.api.users.get("user-2"),
        permit.api.users.get("moved"),
        permit.pdp_api.role_assignments.list(),
    ):
        with pytest.raises((PermitApiError, PermitConnectionError)) as caught:
            await call
        raised.append(caught.value)

    # The redirect was followed, with the key: the redirect response keeps the request
    # headers it was sent with.
    [redirected] = [
        error for error in raised if isinstance(error, PermitApiError) and error.response.history
    ]
    assert redirected.response.history[0].status == 307
    for error in raised:
        assert SENTINEL not in str(error)
        assert SENTINEL not in repr(error)
        assert REDACTED in str(error)
        assert_holds_no_key(error)


def assert_holds_no_key(error: BaseException) -> None:
    """Assert neither `error` nor the aiohttp objects it carries print the key.

    Those are its cause and context, `original_error`, a `PermitApiError`'s response and
    details, the redirect responses in the `history` of any of them, and the traceback of
    `error` with every exception chained under it. The key is looked for as given and in
    lower case.
    """
    shown = [
        str(error),
        repr(error.args),
        repr(getattr(error, "details", None)),
        "".join(traceback.format_exception(error)),
    ]
    carried = [
        error.__cause__,
        error.__context__,
        getattr(error, "original_error", None),
        getattr(error, "_response", None),
    ]
    carried += [redirect for value in carried for redirect in getattr(value, "history", None) or ()]
    for value in carried:
        shown += [repr(value), repr(getattr(value, "args", ()))]
        info = getattr(value, "request_info", None)
        if info is not None:
            shown += [repr(info), str(dict(info.headers))]
    # Every attribute of every chained exception, printed or not.
    shown += [repr(vars(chained)) + repr(chained.args) for chained in chained_exceptions(error)]
    for key in SENTINEL_SPELLINGS:
        assert [text for text in shown if key in text] == []


def chained_exceptions(error: BaseException) -> list[BaseException]:
    """Every exception reachable from `error` through `__cause__` and `__context__`."""
    found: list[BaseException] = []
    pending: list[BaseException | None] = [error]
    while pending:
        current = pending.pop()
        if current is not None and not any(current is seen for seen in found):
            found.append(current)
            pending += [current.__cause__, current.__context__]
    return found


@pytest.mark.parametrize("status", [200, 502])
async def test_a_non_json_answer_raises_without_the_key_in_its_request_headers(
    httpserver: HTTPServer, status: int
) -> None:
    """An answer that isn't JSON raises without the key in its request headers.

    aiohttp keeps the request's headers on the error it raises for it. The SDK's
    exception, its cause and `original_error` don't print the key.
    """
    # Not `serve`, which already answers /allowed with JSON.
    httpserver.expect_request("/v2/api-key/scope", method="GET").respond_with_json(
        {"organization_id": ORG_ID, "project_id": PROJECT_ID, "environment_id": ENV_ID}
    )
    httpserver.expect_request(f"{USERS}/user-3", method="GET").respond_with_data(
        "<html>bad gateway</html>", status=status, content_type="text/html"
    )
    httpserver.expect_request("/allowed", method="POST").respond_with_data(
        "<html>proxy</html>", status=200, content_type="text/html"
    )
    permit = Permit(make_config(httpserver))

    raised: list[BaseException] = []
    for call in (permit.api.users.get("user-3"), permit.check("user-1", "read", "document")):
        with pytest.raises((PermitApiError, PermitConnectionError)) as caught:
            await call
        raised.append(caught.value)

    assert any(error.__cause__ is not None for error in raised)
    for error in raised:
        assert_holds_no_key(error)


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("http://user:secret@pdp.example.com:7766/x", "http://pdp.example.com:7766/x"),
        ("http://user:secret@[::1]:7766", "http://[::1]:7766"),
        ("http://user:secret@pdp.example.com:99999", "http://pdp.example.com:99999"),
        ("http://pdp.example.com:7766", "http://pdp.example.com:7766"),
        ("http://[::1", "<invalid URL>"),
    ],
)
def test_without_userinfo_never_raises(url: str, shown: str) -> None:
    assert without_userinfo(url) == shown


def test_the_init_line_leaves_out_the_url_user_and_password(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    url = httpserver.url_for("").rstrip("/").replace("://", "://proxy-user:proxy-password@")
    config = PermitConfig(
        token=SENTINEL, api_url=url, pdp=url, log={"enable": True, "level": "debug"}
    )

    SyncPermit(config)

    [record] = [r for r in app_sinks.sdk_records() if "SDK initialized" in r["message"]]
    assert "proxy-password" not in record["message"]
    assert "proxy-user" not in record["message"]
    assert httpserver.url_for("").rstrip("/") in record["message"]


def test_wait_for_sync_runs_a_subclass_s_own_setup(httpserver: HTTPServer) -> None:
    class CustomPermit(SyncPermit):
        def __init__(self, config: PermitConfig) -> None:
            super().__init__(config)
            self.custom = True

    permit = CustomPermit(proxied_config(httpserver))
    with permit.wait_for_sync() as waiting:
        assert type(waiting) is CustomPermit
        assert waiting.custom is True


def test_a_short_token_is_not_redacted_from_the_sdk_s_text() -> None:
    redactor = SdkLogger()
    redactor.redact("token")
    redactor.redact(" permit ")

    assert redactor.scrub("bad token for permit.check()") == "bad token for permit.check()"


def test_a_key_of_12_characters_is_redacted_and_one_of_11_is_not() -> None:
    redactor = SdkLogger()
    redactor.redact("a" * 11)
    redactor.redact("b" * 12)

    assert redactor.scrub(f"{'a' * 11} {'b' * 12}") == f"{'a' * 11} {REDACTED}"


@pytest.mark.parametrize("level", ["10", " debug ", "DEBUG"])
def test_a_numeric_or_padded_level_is_read(
    httpserver: HTTPServer, app_sinks: AppSinks, level: str
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    permit = SyncPermit(make_config(httpserver, enable=True, level=level))

    assert permit.check("user-1", "read", "document")

    levels = {record["level"]["name"] for record in app_sinks.sdk_records()}
    assert "DEBUG" in levels
    assert "WARNING" not in levels


def test_an_unknown_level_is_warned_about_once(httpserver: HTTPServer, app_sinks: AppSinks) -> None:
    for _ in range(3):
        # The name test_an_unknown_level_warns_and_logs_at_info uses too: each test starts
        # with no name warned about.
        SyncPermit(make_config(httpserver, enable=True, level="verbose"))

    warnings = [r for r in app_sinks.sdk_records() if "Unknown log level" in r["message"]]
    assert len(warnings) == 1


def echo_the_key_as_a_json_object_key(request: Request) -> Response:
    """An API that rejects the request and puts the key it was sent in an object key."""
    key = json_escaped(request.headers["Authorization"])
    body = f'{{"detail": {{"{key}": "rejected"}}, "error_code": "x"}}'
    return Response(body, status=403, content_type="application/json")


async def test_an_echoed_key_in_a_json_object_key_is_redacted(httpserver: HTTPServer) -> None:
    serve(httpserver)
    httpserver.expect_request(f"{USERS}/user-4", method="GET").respond_with_handler(
        echo_the_key_as_a_json_object_key
    )
    permit = Permit(make_config(httpserver))

    with pytest.raises(PermitApiError) as caught:
        await permit.api.users.get("user-4")

    assert SENTINEL not in str(caught.value)
    assert SENTINEL not in repr(caught.value.details)


def test_a_key_in_the_label_is_redacted(httpserver: HTTPServer, app_sinks: AppSinks) -> None:
    config = make_config(httpserver, enable=True, level="debug", label=f"app {SENTINEL}")

    SyncPermit(config)

    records = app_sinks.sdk_records()
    assert records
    for record in records:
        assert SENTINEL not in record["message"]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(lambda auth: f"<html>rejected key {auth}</html>".encode(), id="html"),
        pytest.param(lambda auth: f'{{"detail": "rejected key {auth}"'.encode(), id="truncated"),
        pytest.param(lambda auth: b"\xff rejected key " + auth.encode(), id="not-utf-8"),
    ],
)
async def test_an_error_body_labelled_json_that_is_not_json_raises_a_permit_api_error(
    httpserver: HTTPServer, body: Callable[[str], bytes]
) -> None:
    serve(httpserver)

    def handler(request: Request) -> Response:
        return Response(
            body(request.headers["Authorization"]),
            status=502,
            content_type="application/json; charset=utf-8",
        )

    httpserver.expect_request(f"{USERS}/user-6", method="GET").respond_with_handler(handler)
    permit = Permit(make_config(httpserver))

    with pytest.raises(PermitApiError) as caught:
        await permit.api.users.get("user-6")

    assert caught.value.status_code == 502
    assert caught.value.details is not None
    assert f"rejected key Bearer {REDACTED}" in caught.value.details["details"]
    assert_holds_no_key(caught.value)


def answer_with_the_key_in_the_content_type(request: Request) -> Response:
    """A 200 answer that isn't JSON, its Content-Type echoing the key the request carried.

    The key is echoed without surrounding whitespace.
    """
    key = request.headers["Authorization"].removeprefix("Bearer ").strip()
    return Response("not json", status=200, content_type=f"text/html; echo={key}")


# A key read from a file may end with a space, which the echo drops.
@pytest.mark.parametrize("token", [SENTINEL, f"{SENTINEL} "], ids=["key", "padded-key"])
async def test_a_connection_error_holds_no_key_from_the_aiohttp_error_text(
    httpserver: HTTPServer, token: str
) -> None:
    """The text of an aiohttp error goes into the message of the PermitConnectionError.

    aiohttp lower-cases the Content-Type it puts in the message of the error it raises for
    an answer that isn't JSON, so the key, which has capital letters, is there in lower case.
    """
    for path in ("/allowed", "/allowed/bulk", "/authorized_users", "/user-permissions"):
        httpserver.expect_request(path, method="POST").respond_with_handler(
            answer_with_the_key_in_the_content_type
        )
    httpserver.expect_request(f"{USERS}/user-7", method="GET").respond_with_handler(
        answer_with_the_key_in_the_content_type
    )
    # After the handlers above: the first one registered for a request answers it.
    serve(httpserver)
    permit = Permit(make_config(httpserver, token=token))
    sync_permit = SyncPermit(make_config(httpserver, token=token))

    calls: list[Callable[[], Any]] = [
        lambda: permit.check("user-1", "read", "document"),
        lambda: permit.bulk_check(BULK),
        lambda: permit.authorized_users("read", "document"),
        lambda: permit.get_user_permissions("user-1"),
        lambda: permit.api.users.get("user-7"),
    ]
    raised: list[PermitConnectionError] = []
    for call in calls:
        with pytest.raises(PermitConnectionError) as caught:
            await call()
        raised.append(caught.value)
    with pytest.raises(PermitConnectionError) as caught:
        sync_permit.check("user-1", "read", "document")
    raised.append(caught.value)

    for error in raised:
        # The aiohttp error's text is in the message, the key replaced.
        assert f"echo={REDACTED}" in str(error)
        assert_holds_no_key(error)


@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
def test_a_subclass_s_own_connect_method_is_not_called_by_the_sdk(
    httpserver: HTTPServer, client_class: type[Permit]
) -> None:
    """The SDK's constructor calls no method an application's subclass may define."""

    class AppPermit(client_class):  # type: ignore[valid-type,misc]
        def _connect(self, url: str) -> str:
            return url

    permit = AppPermit(make_config(httpserver))

    assert permit.api is not None
    assert permit._connect("x") == "x"


def test_an_enabled_client_undoes_only_the_sdk_s_own_disable_once(
    httpserver: HTTPServer, app_sinks: AppSinks
) -> None:
    SyncPermit(make_config(httpserver))
    # Undoes the disable the client above made.
    SyncPermit(make_config(httpserver, enable=True))
    logger.disable("permit")

    # The SDK's own disable was undone already: this one keeps the application's.
    with SyncPermit(make_config(httpserver, enable=True)).wait_for_sync():
        pass

    assert app_sinks.sdk_records() == []


@pytest.mark.parametrize("disabled", ["permit.enforcement", ""], ids=["sdk-module", "all"])
def test_undoing_the_sdk_s_disable_undoes_a_disable_the_application_made_before_it(
    httpserver: HTTPServer, app_sinks: AppSinks, disabled: str
) -> None:
    """Loguru's `logger.disable("permit")` drops every switch set for a module of it.

    So does `logger.enable("permit")`, which the enabled client calls to undo it, and it
    overrides an application-wide `logger.disable("")` for the SDK's records. The README
    says so.
    """
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    logger.disable(disabled)
    try:
        SyncPermit(make_config(httpserver))
        permit = SyncPermit(make_config(httpserver, enable=True, level="debug"))
        assert permit.check("user-1", "read", "document")
    finally:
        logger.enable(disabled)

    modules = {record["name"] for record in app_sinks.sdk_records()}
    assert "permit.enforcement.enforcer" in modules


LAZY_DEBUG_CALLS: list[Any] = [
    pytest.param(lambda permit: permit.check("user-1", "read", "document"), id="check"),
    pytest.param(lambda permit: permit.bulk_check(BULK), id="bulk_check"),
    pytest.param(lambda permit: permit.authorized_users("read", "document"), id="authorized_users"),
    pytest.param(lambda permit: permit.get_user_permissions("user-1"), id="get_user_permissions"),
]


@pytest.mark.parametrize("call", LAZY_DEBUG_CALLS)
@pytest.mark.parametrize("application_enables", [False, True])
def test_a_record_loguru_drops_is_not_built_or_scrubbed(
    httpserver: HTTPServer,
    app_sinks: AppSinks,
    monkeypatch: pytest.MonkeyPatch,
    call: Callable[[SyncPermit], object],
    *,
    application_enables: bool,
) -> None:
    """With the SDK's logging off, its debug records cost nothing to drop.

    The application may still turn them on itself, and then gets them in full.
    """
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    httpserver.expect_request("/allowed/bulk", method="POST").respond_with_json(
        {"allow": [{"allow": True}]}
    )
    httpserver.expect_request("/authorized_users", method="POST").respond_with_json(
        {"resource": "document:*", "tenant": "default", "users": {}}
    )
    httpserver.expect_request("/user-permissions", method="POST").respond_with_json({})
    calls: list[str] = []
    real_scrub = sdk_logger.scrub

    def pformat(value: object, **kwargs: Any) -> str:
        calls.append("pformat")
        return pprint.pformat(value, **kwargs)

    def scrub(text: str) -> str:
        calls.append("scrub")
        return real_scrub(text)

    monkeypatch.setattr("permit.enforcement.enforcer.pformat", pformat)
    monkeypatch.setattr(sdk_logger, "scrub", scrub)
    client = SyncPermit(make_config(httpserver))
    if application_enables:
        logger.enable("permit")

    call(client)

    if application_enables:
        [record] = app_sinks.sdk_records()
        assert record["level"]["name"] == "DEBUG"
        assert "pformat" in calls
        assert "scrub" in calls
    else:
        assert app_sinks.sdk_records() == []
        assert calls == []


@pytest.mark.parametrize("message", [None, 42, b"bytes", ValueError("x")], ids=repr)
def test_a_connection_error_keeps_a_message_that_is_not_a_string(
    httpserver: HTTPServer, message: object
) -> None:
    Permit(make_config(httpserver))

    error = PermitConnectionError(message)

    assert error.args == (message,)


@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
async def test_a_pdp_error_body_that_is_not_utf_8_raises_a_permit_connection_error(
    httpserver: HTTPServer, client_class: type[Permit]
) -> None:
    def handler(request: Request) -> Response:
        body = b"\xff rejected key: " + request.headers["Authorization"].encode()
        return Response(body, status=403, content_type="text/plain; charset=utf-8")

    for path in ("/allowed", "/allowed/bulk", "/authorized_users"):
        httpserver.expect_request(path, method="POST").respond_with_handler(handler)
    permit = client_class(make_config(httpserver))

    for call in (
        lambda: permit.check("user-1", "read", "document"),
        lambda: permit.bulk_check(BULK),
        lambda: permit.authorized_users("read", "document"),
    ):
        with pytest.raises(PermitConnectionError) as caught:
            await resolved(call())
        assert f"rejected key: Bearer {REDACTED}" in str(caught.value)
        assert_holds_no_key(caught.value)


class _RawHandler(socketserver.StreamRequestHandler):
    """Answers a request with the server's raw bytes, then closes the connection."""

    def handle(self) -> None:
        # The request line and headers; any body is left unread.
        line = self.rfile.readline()
        while line not in (b"\r\n", b"\n", b""):
            line = self.rfile.readline()
        self.wfile.write(cast("_RawHttpServer", self.server).reply)


class _RawHttpServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, reply: bytes) -> None:
        super().__init__(("127.0.0.1", 0), _RawHandler)
        self.reply = reply


EMPTY = "Content-Length: 0\r\n\r\n"


def redirect_to(location: str) -> str:
    return f"HTTP/1.1 307 TR\r\nLocation: {location}\r\n{EMPTY}"


LONG = "a" * 9000

# Answers aiohttp can't use, each holding the key. aiohttp keeps the key in the text of
# the error it raises (its message, its args or its URL), or in the parser error it chains
# under it, as a string, as bytes or as a yarl URL.
RAW_ANSWERS = [
    pytest.param(
        "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nBad Header {key}: x\r\n\r\nok", id="bad-header"
    ),
    pytest.param("HTTP/1.1 abc {key}\r\n" + EMPTY, id="bad-status-line"),
    # LineTooLong, which keeps the line as bytes in its args.
    pytest.param("HTTP/1.1 200 OK\r\nX-Long: {key}" + LONG + "\r\n" + EMPTY, id="header-too-long"),
    # InvalidHeader, which keeps the header as bytes in its args.
    pytest.param("HTTP/1.1 200 OK\r\nX-Nul: {key}\x00\r\n" + EMPTY, id="nul-in-header"),
    pytest.param(redirect_to("http://[{key}"), id="invalid-redirect-url"),
    # InvalidUrlRedirectClientError with the URL parsed: a yarl URL in `_url` and `args`.
    pytest.param(redirect_to("http:///{key}"), id="redirect-url-without-host"),
    pytest.param(redirect_to("ftp://host/{key}"), id="non-http-redirect"),
]


@pytest.fixture
def raw_http_server(request: pytest.FixtureRequest) -> Iterator[str]:
    """A server that answers with `request.param`, the key put in it; yields its URL."""
    server = _RawHttpServer(request.param.format(key=SENTINEL).encode())
    # A short poll interval: shutdown() waits for the next poll.
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("raw_http_server", RAW_ANSWERS, indirect=True)
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda permit: permit.check("user-1", "read", "document"), id="pdp"),
        pytest.param(lambda permit: permit.api.users.get("user-1"), id="api"),
    ],
)
@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
async def test_an_aiohttp_error_and_the_errors_chained_under_it_hold_no_key(
    raw_http_server: str, client_class: type[Permit], call: Callable[[Permit], object]
) -> None:
    permit = client_class(
        PermitConfig(token=SENTINEL, api_url=raw_http_server, pdp=raw_http_server)
    )

    with pytest.raises(PermitConnectionError) as caught:
        await resolved(call(permit))

    assert caught.value.original_error is not None
    assert_holds_no_key(caught.value)
    # The case still reaches a key to replace.
    shown = [
        repr(vars(chained)) + repr(chained.args) for chained in chained_exceptions(caught.value)
    ]
    assert REDACTED in "".join(shown)


# Functions that raise and catch in a module of aiohttp's, as aiohttp's own code does: the
# SDK changes only exceptions raised and caught within its request.
AIOHTTP_DOUBLE_SOURCE = """
import aiohttp


def context_only(key):
    try:
        try:
            raise ValueError(f"inner {key}")
        except ValueError:
            raise aiohttp.ClientError("outer")
    except aiohttp.ClientError as error:
        return error


def raised(error):
    try:
        raise error
    except BaseException as caught:
        return caught
"""
aiohttp_double = types.ModuleType("aiohttp._test_double")
exec(AIOHTTP_DOUBLE_SOURCE, aiohttp_double.__dict__)  # noqa: S102 - a fixed test double


def test_an_error_chained_only_as_the_context_is_scrubbed(httpserver: HTTPServer) -> None:
    Permit(make_config(httpserver))
    error = aiohttp_double.context_only(SENTINEL)
    inner = error.__context__
    assert error.__cause__ is None
    assert isinstance(inner, ValueError)

    assert scrub_request_info(error)

    assert inner.args == (f"inner {REDACTED}",)


# A walk that never ends can't be stopped in a thread, so this runs in its own process.
CAUSE_CYCLE_APP = f"""
import sys
import types

import aiohttp

from permit import Permit
from permit.exceptions import scrub_request_info

double = types.ModuleType("aiohttp._test_double")
exec({AIOHTTP_DOUBLE_SOURCE!r}, double.__dict__)
Permit(token="{SENTINEL}")
first = double.raised(aiohttp.ClientError("first {SENTINEL}"))
second = double.raised(aiohttp.ClientError("second {SENTINEL}"))
first.__cause__ = second
second.__cause__ = first
assert scrub_request_info(first)
print(first.args[0], second.args[0])
"""


def test_a_cause_cycle_is_walked_once(tmp_path: Path) -> None:
    app = tmp_path / "app.py"
    app.write_text(CAUSE_CYCLE_APP)

    result = subprocess.run(
        [sys.executable, str(app)], capture_output=True, text=True, timeout=15, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["first", REDACTED, "second", REDACTED]


def test_an_error_whose_text_cannot_be_replaced_is_not_attached(httpserver: HTTPServer) -> None:
    class FixedArgsError(aiohttp.ClientError):
        @property
        def args(self) -> tuple[object, ...]:  # type: ignore[override]
            return (f"fixed {SENTINEL}",)

    Permit(make_config(httpserver))
    original = aiohttp_double.raised(FixedArgsError())

    error = PermitConnectionError("the request failed", error=original)

    assert error.original_error is not original
    assert SENTINEL not in repr(error.original_error)
    assert "could not be removed" in str(error.original_error)


def raise_(error: BaseException) -> NoReturn:
    raise error


@dataclasses.dataclass(frozen=True)
class FrozenAppError(Exception):
    """An application's exception that can't be changed."""

    detail: str


class AppHeadersError(Exception):
    """An application's exception with a headers dict whose values aren't all strings."""

    def __init__(self) -> None:
        super().__init__(f"the application's own text, with the key {SENTINEL}")
        self.headers = {"Retry-After": 120, "X-Echo": SENTINEL}


class AppFixedArgsError(Exception):
    """An application's exception whose args can't be set."""

    @property
    def args(self) -> tuple[object, ...]:  # type: ignore[override]
        return (f"fixed {SENTINEL}",)


@pytest.mark.parametrize(
    "app_error",
    [
        pytest.param(lambda: FrozenAppError(f"frozen {SENTINEL}"), id="frozen-dataclass"),
        pytest.param(AppHeadersError, id="headers-with-an-int"),
        pytest.param(AppFixedArgsError, id="read-only-args"),
    ],
)
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda permit: permit.check("user-1", "read", "document"), id="pdp"),
        pytest.param(lambda permit: permit.api.users.get("user-1"), id="api"),
    ],
)
@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
@pytest.mark.parametrize(
    "raw_http_server", [pytest.param(redirect_to("ftp://host/{key}"), id="redirect")], indirect=True
)
async def test_an_exception_the_application_is_handling_is_left_alone(
    raw_http_server: str,
    client_class: type[Permit],
    call: Callable[[Permit], object],
    app_error: Callable[[], Exception],
) -> None:
    """An application may call the SDK while it handles an exception of its own.

    aiohttp's error then keeps that exception as its context: here, the error for a
    redirect to a URL that isn't HTTP, which aiohttp raises in the caller's task. The SDK
    still raises PermitConnectionError, and doesn't change the application's exception,
    even where it holds the key.
    """
    url = raw_http_server
    permit = client_class(PermitConfig(token=SENTINEL, api_url=url, pdp=url))
    handled = app_error()
    before = (repr(vars(handled)), repr(handled.args))

    try:
        raise_(handled)
    except Exception:
        with pytest.raises(PermitConnectionError) as caught:
            await resolved(call(permit))

    # The application's exception is in the chain, unchanged.
    assert any(chained is handled for chained in chained_exceptions(caught.value))
    assert (repr(vars(handled)), repr(handled.args)) == before
    if isinstance(handled, AppHeadersError):
        assert type(handled.headers) is dict
    assert caught.value.original_error is not None
    assert SENTINEL not in repr(vars(caught.value.original_error))


@pytest.mark.parametrize(
    "raw_http_server", [pytest.param(redirect_to("ftp://host/{key}"), id="redirect")], indirect=True
)
@pytest.mark.parametrize(
    "call",
    [*LAZY_DEBUG_CALLS, pytest.param(lambda permit: permit.api.users.get("user-1"), id="api")],
)
@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
async def test_an_error_that_cannot_be_scrubbed_is_neither_attached_nor_the_cause(
    raw_http_server: str,
    client_class: type[Permit],
    call: Callable[[Permit], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("permit.exceptions.scrub_request_info", lambda _: False)
    url = raw_http_server
    permit = client_class(PermitConfig(token=SENTINEL, api_url=url, pdp=url))

    with pytest.raises(PermitConnectionError) as caught:
        await resolved(call(permit))

    replacement = caught.value.original_error
    assert "could not be removed" in str(replacement)
    assert caught.value.__cause__ is replacement
    assert SENTINEL not in "".join(traceback.format_exception(caught.value))
