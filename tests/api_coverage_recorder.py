"""A pytest plugin that records every HTTP request the SDK sends (PER-16337).

The API coverage report (.github/scripts/api_coverage.py) learns which API
operation each SDK method calls from the requests the tests actually send: the
offline wire tests for the coverage column, the end-to-end tests for the column of
operations exercised against a real backend and PDP.

The plugin is always loaded (tests/conftest.py names it in ``pytest_plugins``) and
does nothing unless a record file is given, with ``--api-coverage-record PATH`` or
the ``PERMIT_API_COVERAGE_RECORD`` environment variable (the option wins). A normal
test run is unchanged.

When enabled, it adds an aiohttp trace config to every ``aiohttp.ClientSession``
created during the session, which is how every SDK request is sent, through the
async and the blocking client alike. The record is JSON Lines:

* a ``header`` line with the format version;
* one ``request`` line per request: the HTTP method, the raw (still percent-encoded)
  URL path without its query string, the response status (null when no response
  arrived), the test's node id and whether that test is marked ``e2e``;
* a ``session`` line written when the session finishes, with its exit status and
  the number of tests that ran. A record without it comes from a session that did
  not finish, and the report refuses to read it.

Only the method and path are kept: the query string, headers and bodies stay out
of the record, and so out of the CI artifact it is uploaded as.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import aiohttp
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import SimpleNamespace

    from yarl import URL

RECORD_OPTION = "--api-coverage-record"
RECORD_ENV = "PERMIT_API_COVERAGE_RECORD"
# Bumped when a record line changes shape; the report rejects other versions.
FORMAT_VERSION = 1
PLUGIN_NAME = "api-coverage-recorder"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the option that turns recording on."""
    parser.getgroup("api coverage").addoption(
        RECORD_OPTION,
        metavar="PATH",
        default=None,
        help=(
            "Write every HTTP request the SDK sends to PATH (JSON Lines), for the API "
            f"coverage report. Also read from the {RECORD_ENV} environment variable."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Start recording when a record file is given; otherwise do nothing."""
    target = config.getoption(RECORD_OPTION) or os.environ.get(RECORD_ENV)
    if not target:
        return
    recorder = RequestRecorder(Path(target))
    config.pluginmanager.register(recorder, PLUGIN_NAME)
    config.add_cleanup(recorder.close)


class RequestRecorder:
    """Writes one record line per request, attributed to the test that sent it."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file: IO[str] | None = path.open("w", encoding="utf-8")
        self._lock = threading.Lock()
        self._test: str | None = None
        self._e2e = False
        self._tests = 0
        self._write({"kind": "header", "version": FORMAT_VERSION})

        trace = aiohttp.TraceConfig()
        trace.on_request_start.append(self._on_request_start)
        trace.on_request_end.append(self._on_request_end)
        trace.on_request_exception.append(self._on_request_exception)
        original_init = aiohttp.ClientSession.__init__

        def traced_init(session: aiohttp.ClientSession, *args: Any, **kwargs: Any) -> None:
            configs = list(kwargs.pop("trace_configs", None) or [])
            original_init(session, *args, trace_configs=[*configs, trace], **kwargs)

        self._patch = pytest.MonkeyPatch()
        self._patch.setattr(aiohttp.ClientSession, "__init__", traced_init)

    def close(self) -> None:
        """Stop tracing new sessions and close the record file."""
        self._patch.undo()
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item) -> Generator[None, object, object]:
        """Attribute the requests of a test's setup, call and teardown to that test."""
        self._test = item.nodeid
        self._e2e = item.get_closest_marker("e2e") is not None
        self._tests += 1
        try:
            return (yield)
        finally:
            self._test = None
            self._e2e = False

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        """Write the line that marks the record as complete."""
        self._write({"kind": "session", "exitstatus": int(exitstatus), "tests": self._tests})

    async def _on_request_start(
        self,
        _session: aiohttp.ClientSession,
        context: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        context.api_coverage = {
            "method": params.method.upper(),
            "path": _raw_path(params.url),
            "test": self._test,
            "e2e": self._e2e,
        }

    async def _on_request_end(
        self,
        _session: aiohttp.ClientSession,
        context: SimpleNamespace,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        self._write_request(context, params.response.status)

    async def _on_request_exception(
        self,
        _session: aiohttp.ClientSession,
        context: SimpleNamespace,
        _params: aiohttp.TraceRequestExceptionParams,
    ) -> None:
        self._write_request(context, None)

    def _write_request(self, context: SimpleNamespace, status: int | None) -> None:
        started = getattr(context, "api_coverage", None)
        if started is not None:
            self._write({"kind": "request", **started, "status": status})

    def _write(self, line: dict[str, Any]) -> None:
        with self._lock:
            if self._file is None:
                return
            self._file.write(json.dumps(line, sort_keys=True) + "\n")
            self._file.flush()


def _raw_path(url: URL) -> str:
    """The URL's path as sent, percent-encoding kept, so a ``%2F`` in a key stays one segment."""
    return url.raw_path
