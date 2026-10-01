"""Tests for the request recorder the API coverage report reads (tests/api_coverage_recorder.py).

Each test runs a small pytest session in a fresh interpreter, with the recorder loaded as
a plugin, and checks the record it writes. A separate interpreter keeps those sessions'
requests out of this session's own record when the coverage job runs the suite with the
recorder on, and keeps the recorder's patch of aiohttp out of this process.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tests.api_coverage_recorder import FORMAT_VERSION, RECORD_ENV, RECORD_OPTION

REPO_ROOT = Path(__file__).resolve().parents[1]

# The inner session's tests. Every request goes to pytest-httpserver's local server,
# except the one that is refused on purpose.
INNER_TESTS = textwrap.dedent(
    """
    import asyncio
    import re
    from concurrent.futures import ThreadPoolExecutor

    import aiohttp
    import pytest
    from yarl import URL

    from permit.sync import Permit
    from tests.utils import offline_config


    async def send(method, url, **session_kwargs):
        async with aiohttp.ClientSession(**session_kwargs) as session:
            async with session.request(method, URL(url, encoded=True)) as response:
                return response.status


    @pytest.fixture(autouse=True)
    def answer_everything(httpserver):
        httpserver.expect_request(re.compile(".*")).respond_with_json({}, status=201)


    def test_encoded_path(httpserver):
        url = httpserver.url_for("/v2/users/a%2Fb") + "?secret=1"
        assert asyncio.run(send("GET", url)) == 201


    @pytest.mark.e2e
    def test_marked_e2e(httpserver):
        asyncio.run(send("POST", httpserver.url_for("/allowed")))


    def test_in_another_thread(httpserver):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, send("DELETE", httpserver.url_for("/threaded"))).result()


    def test_blocking_client(httpserver):
        permit = Permit(offline_config(httpserver.url_for("").rstrip("/")))
        try:
            permit.api.users.get("u1")
        except Exception:
            pass


    def test_refused():
        with pytest.raises(aiohttp.ClientError):
            asyncio.run(send("PUT", "http://127.0.0.1:1/refused"))


    def test_own_trace_configs_still_run(httpserver):
        seen = []

        async def on_start(session, context, params):
            seen.append(params.url.path)

        trace = aiohttp.TraceConfig()
        trace.on_request_start.append(on_start)
        asyncio.run(send("GET", httpserver.url_for("/traced"), trace_configs=[trace]))
        assert seen == ["/traced"]


    def test_fails():
        assert False
    """
)

UNPATCHED = textwrap.dedent(
    """
    import aiohttp


    def test_aiohttp_is_untouched(pytestconfig):
        assert aiohttp.ClientSession.__init__.__qualname__ == "ClientSession.__init__"
        assert pytestconfig.pluginmanager.get_plugin("api-coverage-recorder") is None
    """
)


def run_session(
    tmp_path: Path, tests: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run tests in a pytest session of their own, with the recorder plugin loaded."""
    (tmp_path / "test_inner.py").write_text(tests, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    e2e: marked\n", encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if key != RECORD_ENV}
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(REPO_ROOT), environment.get("PYTHONPATH")])
    )
    environment.update(env or {})
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests.api_coverage_recorder",
            "-p",
            "no:cacheprovider",
            "-c",
            str(tmp_path / "pytest.ini"),
            "--rootdir",
            str(tmp_path),
            "-q",
            str(tmp_path / "test_inner.py"),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=environment,
        timeout=120,
    )


def read_record(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_the_record_holds_every_request_with_the_test_that_sent_it(tmp_path: Path) -> None:
    record = tmp_path / "out" / "record.jsonl"
    ignored = tmp_path / "from-env.jsonl"
    completed = run_session(
        tmp_path, INNER_TESTS, RECORD_OPTION, str(record), env={RECORD_ENV: str(ignored)}
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "1 failed, 6 passed" in completed.stdout
    assert not ignored.exists(), "the option must win over the environment variable"

    lines = read_record(record)
    assert lines[0] == {"kind": "header", "version": FORMAT_VERSION}
    assert lines[-1] == {"kind": "session", "exitstatus": 1, "tests": 7}
    requests = [(line["test"].split("::")[-1], line) for line in lines[1:-1]]
    test_file = "test_inner.py"
    assert all(line["test"].startswith(test_file) for _, line in requests)
    assert [
        (test, line["method"], line["path"], line["status"], line["e2e"]) for test, line in requests
    ] == [
        ("test_encoded_path", "GET", "/v2/users/a%2Fb", 201, False),
        ("test_marked_e2e", "POST", "/allowed", 201, True),
        ("test_in_another_thread", "DELETE", "/threaded", 201, False),
        ("test_blocking_client", "GET", "/v2/facts/test-project/test-env/users/u1", 201, False),
        ("test_refused", "PUT", "/refused", None, False),
        ("test_own_trace_configs_still_run", "GET", "/traced", 201, False),
    ]
    assert {key for _, line in requests for key in line} == {
        "kind",
        "method",
        "path",
        "status",
        "test",
        "e2e",
    }


def test_the_environment_variable_turns_recording_on(tmp_path: Path) -> None:
    record = tmp_path / "record.jsonl"
    completed = run_session(tmp_path, INNER_TESTS, "-k", "encoded", env={RECORD_ENV: str(record)})
    assert completed.returncode == 0, completed.stdout + completed.stderr
    lines = read_record(record)
    assert [line["kind"] for line in lines] == ["header", "request", "session"]
    assert lines[1]["path"] == "/v2/users/a%2Fb"
    assert lines[2] == {"kind": "session", "exitstatus": 0, "tests": 1}


def test_without_a_record_file_the_recorder_does_nothing(tmp_path: Path) -> None:
    completed = run_session(tmp_path, UNPATCHED)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert list(tmp_path.glob("**/*.jsonl")) == []


def test_the_suite_loads_the_recorder(pytestconfig: pytest.Config) -> None:
    """tests/conftest.py registers the plugin, so the coverage job's option exists."""
    assert pytestconfig.pluginmanager.get_plugin("tests.api_coverage_recorder") is not None
    assert pytestconfig.getoption(RECORD_OPTION, default="unregistered") != "unregistered"
