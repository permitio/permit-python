"""Offline tests for the SDK's logging (PER-16680).

The SDK logs through loguru's process-wide logger and adds no sink of its own. These tests
add sinks the way an application does, and read what reached them: a text sink on stderr in
loguru's default format, read through capsys, and a serialized (JSON) sink. Every request is
served by a local pytest_httpserver.
"""

import json
import subprocess
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from loguru import logger
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

from permit import Permit, PermitConfig
from permit.enforcement.enforcer import CheckQuery
from permit.exceptions import PermitConnectionError
from permit.sync import Permit as SyncPermit
from permit.utils.sdk_logger import REDACTED, SdkLogger, sdk_logger

SENTINEL = "permit_key_SENTINEL_9f8e7d6c5b4a39281706f5e4d3c2b1a0"
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
def isolated_logging() -> Iterator[None]:
    """Start as a fresh process does, and put the SdkLogger and loguru's switches back after.

    Restoring loguru's switch for "permit" also drops any switch a test set for a module of
    the package.
    """
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


@pytest.mark.parametrize("enabled_by", ["config", "application"])
async def test_an_api_key_the_pdp_echoes_back_is_redacted(
    httpserver: HTTPServer, app_sinks: AppSinks, enabled_by: str
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_handler(echo_the_key)
    if enabled_by == "config":
        permit = Permit(make_config(httpserver, enable=True))
    else:
        # A client created with logging disabled, whose records the application turns on.
        permit = Permit(make_config(httpserver))
        logger.enable("permit")

    with pytest.raises(PermitConnectionError) as raised:
        await permit.check("user-1", "read", "document")

    [record] = [record for record in app_sinks.sdk_records() if record["level"]["name"] == "ERROR"]
    assert f"rejected key: Bearer {REDACTED}" in record["message"]
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
    ],
)
async def test_level_drops_the_sdk_records_below_it(
    httpserver: HTTPServer, app_sinks: AppSinks, log: dict[str, str], expected_levels: set[str]
) -> None:
    serve(httpserver)

    await use_async_client(Permit(make_config(httpserver, enable=True, **log)))
    logger.debug("an application record")

    assert app_sinks.sdk_levels() == expected_levels
    # The application's own records are not the SDK's to filter.
    assert "an application record" in [record["message"] for record in app_sinks.records()]


def test_an_unknown_level_fails_when_the_client_is_created(httpserver: HTTPServer) -> None:
    with pytest.raises(ValueError, match=r"Invalid log level 'verbose'"):
        SyncPermit(make_config(httpserver, enable=True, level="verbose"))


def test_the_traceback_of_a_failed_client_creation_hides_the_api_key(
    httpserver: HTTPServer,
) -> None:
    lines: list[str] = []
    # diagnose=True, loguru's default, prints the value of each name on every line of the
    # traceback, and the SDK's frames pass the config around.
    sink_id = logger.add(lines.append, diagnose=True, backtrace=True)
    config = make_config(httpserver, enable=True, level="verbose")
    try:
        try:
            SyncPermit(config)
        except ValueError:
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
