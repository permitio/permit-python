"""Offline tests of the sync client's lifecycle: its background thread, close() and `with`.

permit.sync.Permit runs every blocking call on an event loop in a daemon thread of its own,
so that its calls share HTTP connections (PER-16344). These tests read what can be observed
from outside: the connections a local keep-alive server counts, the state of the client's
thread, the warnings issued, and how a separate interpreter exits.
"""

import asyncio
import contextvars
import gc
import os
import subprocess
import sys
import threading
import time
import traceback
import warnings
import weakref
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pytest_httpserver import HTTPServer

from permit.config import PermitConfig
from permit.sync import Permit as SyncPermit
from permit.utils.deprecation import deprecated
from permit.utils.http_sessions import LoopSessions
from permit.utils.sync import SyncClass, _background_loop_of, _BackgroundLoop, _LoopThread
from tests.keepalive_server import KeepAliveServer
from tests.utils import FACTS, offline_config

REPO_ROOT = Path(__file__).resolve().parents[1]
LOOP_THREAD_NAME = "permit-sync-loop"


@pytest.fixture
def server() -> Iterator[KeepAliveServer]:
    with KeepAliveServer() as server:
        yield server


@pytest.fixture
def permit(server: KeepAliveServer) -> Iterator[SyncPermit]:
    client = SyncPermit(offline_config(server.url))
    yield client
    close_within(client)


def close_within(client: SyncPermit, timeout: float = 5.0) -> None:
    """Close `client`, failing instead of waiting forever if its loop thread is stuck.

    A regression that deadlocks the thread, such as a blocking call the client lets wait for
    its own thread, would otherwise hang the test session here. The stuck thread is a
    daemon, and close() has already left the exit hook nothing to wait for.
    """
    closing = threading.Thread(target=client.close, daemon=True)
    closing.start()
    closing.join(timeout)
    assert not closing.is_alive(), "close() did not return: the client's loop thread is stuck"


def loop_thread(client: SyncPermit) -> threading.Thread | None:
    """The client's background thread, or None while it has none."""
    running = client._background_loop._thread
    return None if running is None else running.thread


def started_loop_threads(before: list[threading.Thread]) -> list[threading.Thread]:
    """The background loop threads running now that were not in `before`."""
    return [
        thread
        for thread in threading.enumerate()
        if thread.name == LOOP_THREAD_NAME and thread not in before
    ]


def wait_until_stopped(thread: threading.Thread, timeout: float = 5.0) -> None:
    """Wait for `thread` to end, a slice at a time.

    On a free-threaded build, an object that another thread releases is freed by the thread
    that created it, once that thread runs again. So a collected client's loop is only
    stopped when this thread wakes up, which one long join() would not let it do.
    """
    deadline = time.monotonic() + timeout
    while thread.is_alive() and time.monotonic() < deadline:
        thread.join(timeout=0.05)


def check(client: SyncPermit) -> bool:
    return client.check("user", "read", "document")


def user_payload(key: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    ids = {name: str(uuid4()) for name in ("id", "organization_id", "project_id", "environment_id")}
    return {"key": key, **ids, "created_at": now, "updated_at": now}


# --- the background thread ------------------------------------------------------------


def test_the_client_starts_no_thread_before_its_first_call(permit: SyncPermit) -> None:
    assert loop_thread(permit) is None


def test_the_calls_of_a_client_run_on_one_daemon_thread(permit: SyncPermit) -> None:
    before = threading.enumerate()

    assert check(permit) is True
    thread = loop_thread(permit)
    assert check(permit) is True

    assert thread is not None
    assert thread.is_alive()
    assert thread.daemon
    assert loop_thread(permit) is thread
    assert started_loop_threads(before) == [thread]


def test_many_threads_share_one_client_and_its_thread(
    permit: SyncPermit, server: KeepAliveServer
) -> None:
    threads, calls = 16, 10
    all_started = threading.Barrier(threads)
    before = threading.enumerate()

    def caller(index: int) -> list[bool]:
        all_started.wait(timeout=10)
        return [permit.check(f"user-{index}-{call}", "read", "document") for call in range(calls)]

    with ThreadPoolExecutor(max_workers=threads) as executor:
        results = list(executor.map(caller, range(threads)))

    assert results == [[True] * calls] * threads
    assert len(server.requests) == threads * calls
    assert started_loop_threads(before) == [loop_thread(permit)]


def test_a_call_from_a_thread_that_runs_an_event_loop(permit: SyncPermit) -> None:
    """The caller's loop is blocked for the call, which runs on the client's thread."""

    async def main() -> tuple[bool, threading.Thread]:
        return check(permit), threading.current_thread()

    allowed, caller = asyncio.run(main())

    assert allowed is True
    assert loop_thread(permit) not in (None, caller)


def sync_api_objects(root: object) -> list[object]:
    """Every object of a `SyncClass` class that `root` holds, through instance attributes."""
    found: list[object] = []
    pending, seen = [root], set()
    while pending:
        obj = pending.pop()
        if id(obj) in seen or not hasattr(obj, "__dict__"):
            continue
        seen.add(id(obj))
        if isinstance(type(obj), SyncClass):
            found.append(obj)
        pending.extend(
            value for value in vars(obj).values() if value.__class__.__module__.startswith("permit")
        )
    return found


@pytest.mark.parametrize("copy", [False, True], ids=["client", "wait_for_sync copy"])
def test_every_blocking_api_object_of_the_client_runs_on_its_loop(
    config: PermitConfig, *, copy: bool
) -> None:
    config.proxy_facts_via_pdp = True
    client = SyncPermit(config)
    with client.wait_for_sync() as waiting:
        objects = sync_api_objects(waiting if copy else client)

    # The enforcer, permit.api and its 19 sub-APIs, permit.elements and the PDP's role
    # assignments.
    assert len(objects) >= 23
    assert [obj for obj in objects if _background_loop_of(obj) is not client._background_loop] == []


@pytest.mark.parametrize(
    ("path", "response", "call"),
    [
        ("/allowed", {"allow": True}, lambda client: client.check("u", "read", "document")),
        (f"{FACTS}/users/u", None, lambda client: client.api.users.get("u")),
        ("/local/role_assignments", [], lambda client: client.pdp_api.role_assignments.list()),
    ],
    ids=["check", "api.users.get", "pdp_api.role_assignments.list"],
)
def test_a_call_through_any_api_starts_the_client_thread(
    httpserver: HTTPServer,
    config: PermitConfig,
    path: str,
    response: object,
    call: Callable[[SyncPermit], object],
) -> None:
    httpserver.expect_oneshot_request(path).respond_with_json(
        user_payload("u") if response is None else response
    )
    with SyncPermit(config) as client:
        call(client)
        thread = loop_thread(client)

    assert thread is not None
    assert not thread.is_alive()
    httpserver.check_assertions()


# --- close() and `with` ---------------------------------------------------------------


def test_close_stops_and_joins_the_thread(permit: SyncPermit) -> None:
    check(permit)
    thread = loop_thread(permit)

    permit.close()

    assert thread is not None
    assert not thread.is_alive()
    assert loop_thread(permit) is None


def test_close_can_be_called_twice_and_before_any_call(server: KeepAliveServer) -> None:
    unused = SyncPermit(offline_config(server.url))
    unused.close()
    unused.close()
    used = SyncPermit(offline_config(server.url))
    check(used)
    used.close()
    used.close()

    assert loop_thread(unused) is None
    assert loop_thread(used) is None


def test_a_call_after_close_starts_a_new_thread(permit: SyncPermit) -> None:
    check(permit)
    first = loop_thread(permit)
    permit.close()

    assert check(permit) is True
    second = loop_thread(permit)

    assert second is not None
    assert second is not first
    assert second.is_alive()


def test_a_with_block_gives_the_client_and_closes_it(server: KeepAliveServer) -> None:
    client = SyncPermit(offline_config(server.url))

    with client as entered:
        check(entered)
        thread = loop_thread(entered)

    assert entered is client
    assert thread is not None
    assert not thread.is_alive()


def test_a_with_block_that_raises_still_closes_the_client(
    server: KeepAliveServer,
) -> None:
    client = SyncPermit(offline_config(server.url))
    check(client)
    thread = loop_thread(client)

    def fail_in_a_with_block() -> None:
        with client:
            raise LookupError

    with pytest.raises(LookupError):
        fail_in_a_with_block()

    assert thread is not None
    assert not thread.is_alive()


def test_async_with_is_refused(server: KeepAliveServer) -> None:
    client = SyncPermit(offline_config(server.url))

    async def enter() -> None:
        # The mistake a type checker reports too: this checks what it does at runtime.
        async with client:  # type: ignore[misc]
            check(client)

    with pytest.raises(TypeError, match=r"use `with Permit\(\.\.\.\) as permit:`"):
        asyncio.run(enter())
    assert loop_thread(client) is None
    assert server.opened == 0


def test_close_waits_for_a_call_in_flight(permit: SyncPermit, server: KeepAliveServer) -> None:
    server.respond("/allowed", {"allow": True}, delay=0.5)
    with ThreadPoolExecutor(max_workers=1) as executor:
        in_flight = executor.submit(check, permit)
        assert server.wait_for_requests(1)
        permit.close()

        assert in_flight.result(timeout=5) is True


def wait_until_closing(client: SyncPermit, timeout: float = 5.0) -> None:
    """Wait until a close() of `client` has started stopping its thread."""
    deadline = time.monotonic() + timeout
    while client._background_loop._closing is None:
        assert time.monotonic() < deadline, "close() did not start"
        time.sleep(0.01)


def in_a_daemon_thread(function: Callable[[], object]) -> Future[object]:
    """Call `function` in a daemon thread, which cannot hold up the exit if it gets stuck."""
    outcome: Future[object] = Future()

    def call() -> None:
        try:
            outcome.set_result(function())
        except Exception as error:
            outcome.set_exception(error)

    threading.Thread(target=call, daemon=True).start()
    return outcome


def test_a_call_made_during_close_waits_for_it_then_starts_a_new_thread(
    permit: SyncPermit, server: KeepAliveServer
) -> None:
    server.respond("/allowed", {"allow": True}, delay=0.5)
    in_flight = in_a_daemon_thread(lambda: check(permit))
    assert server.wait_for_requests(1)
    first = loop_thread(permit)
    closing = in_a_daemon_thread(permit.close)
    wait_until_closing(permit)

    during_close = in_a_daemon_thread(lambda: check(permit))

    assert in_flight.result(timeout=5) is True
    assert closing.result(timeout=5) is None
    assert during_close.result(timeout=5) is True
    second = loop_thread(permit)
    assert first is not None
    assert not first.is_alive()
    assert second not in (None, first)
    assert (server.opened, server.wait_until_closed(1)) == (2, 1)


def test_a_second_close_returns_once_the_first_has_stopped_the_thread(
    permit: SyncPermit, server: KeepAliveServer
) -> None:
    server.respond("/allowed", {"allow": True}, delay=0.5)
    in_flight = in_a_daemon_thread(lambda: check(permit))
    assert server.wait_for_requests(1)
    thread = loop_thread(permit)
    first_close = in_a_daemon_thread(permit.close)
    wait_until_closing(permit)

    second_close = in_a_daemon_thread(permit.close)

    assert second_close.result(timeout=5) is None
    assert thread is not None
    assert not thread.is_alive()
    assert first_close.result(timeout=5) is None
    assert in_flight.result(timeout=5) is True
    assert loop_thread(permit) is None


def test_a_blocking_call_on_the_thread_a_close_stops_raises_instead_of_deadlocking(
    permit: SyncPermit, server: KeepAliveServer
) -> None:
    server.respond("/allowed", {"allow": True}, delay=0.5)
    in_flight = in_a_daemon_thread(lambda: check(permit))
    assert server.wait_for_requests(1)
    stopping = permit._background_loop._thread
    assert stopping is not None
    closing = in_a_daemon_thread(permit.close)
    wait_until_closing(permit)
    outcome: Future[object] = Future()

    def call() -> None:
        try:
            outcome.set_result(check(permit))
        except Exception as error:
            outcome.set_exception(error)

    stopping.loop.call_soon_threadsafe(call, context=contextvars.Context())
    error = outcome.exception(timeout=5)

    assert isinstance(error, RuntimeError)
    assert "own event loop thread" in str(error)
    assert closing.result(timeout=5) is None
    assert in_flight.result(timeout=5) is True


def test_close_closes_the_connections(permit: SyncPermit, server: KeepAliveServer) -> None:
    check(permit)

    permit.close()

    assert server.wait_until_closed(1) == 1


def test_closing_a_wait_for_sync_copy_leaves_its_client_thread_and_connection_open(
    server: KeepAliveServer,
) -> None:
    """A copy runs on its client's thread and connections, and leaves closing them to it."""
    config = offline_config(server.url)
    config.proxy_facts_via_pdp = True
    client = SyncPermit(config)
    with client.wait_for_sync() as waiting:
        assert check(waiting) is True
        thread = loop_thread(client)
        assert loop_thread(waiting) is thread
        waiting.close()
        waiting.close()

    assert thread is not None
    assert thread.is_alive()
    assert check(client) is True
    assert loop_thread(client) is thread
    assert (server.opened, server.closed) == (1, 0)

    client.close()

    assert not thread.is_alive()
    assert server.wait_until_closed(1) == 1


# --- errors and re-entrancy ------------------------------------------------------------


def test_an_error_keeps_its_type_and_traceback(permit: SyncPermit) -> None:
    with pytest.raises(ValueError, match="invalid resource string") as caught:
        permit.check("user", "read", "too:many:parts")

    frames = [
        (Path(frame.filename).name, frame.name)
        for frame in traceback.extract_tb(caught.value.__traceback__)
    ]
    assert ("enforcer.py", "_resource_from_string") in frames
    assert (Path(__file__).name, test_an_error_keeps_its_type_and_traceback.__name__) in frames
    assert loop_thread(permit) is not None


def test_a_timeout_keeps_its_traceback_and_cause(server: KeepAliveServer) -> None:
    """On Python 3.11 and 3.12, asyncio would hand the caller a bare copy of the TimeoutError."""
    server.respond("/allowed", {"allow": True}, delay=1.5)
    config = offline_config(server.url)
    config.pdp_timeout = 1

    with SyncPermit(config) as client, pytest.raises(asyncio.TimeoutError) as caught:
        check(client)

    frames = [
        (Path(frame.filename).name, frame.name)
        for frame in traceback.extract_tb(caught.value.__traceback__)
    ]
    assert ("enforcer.py", "check") in frames
    assert (Path(__file__).name, test_a_timeout_keeps_its_traceback_and_cause.__name__) in frames
    assert caught.value.__cause__ is not None


def test_a_client_whose_call_raised_is_freed_by_reference_counting(server: KeepAliveServer) -> None:
    """The exception a call raised leaves no reference cycle that would hold the client."""
    client = SyncPermit(offline_config(server.url))
    with pytest.raises(ValueError, match="invalid resource string"):
        client.check("user", "read", "too:many:parts")
    freed = weakref.ref(client)

    gc.disable()
    try:
        del client
        assert freed() is None
    finally:
        gc.enable()


def run_on_client_thread(client: SyncPermit, function: Callable[[], object]) -> Future[object]:
    """Call `function` on the client's thread, in a fresh context, as a loop callback would."""
    running = client._background_loop._thread
    assert running is not None
    outcome: Future[object] = Future()

    def call() -> None:
        try:
            outcome.set_result(function())
        except Exception as error:
            outcome.set_exception(error)

    running.loop.call_soon_threadsafe(call, context=contextvars.Context())
    return outcome


def test_a_blocking_call_on_the_client_thread_raises_instead_of_deadlocking(
    permit: SyncPermit,
) -> None:
    check(permit)

    outcome = run_on_client_thread(permit, lambda: check(permit))
    error = outcome.exception(timeout=5)

    assert isinstance(error, RuntimeError)
    assert "own event loop thread" in str(error)
    assert check(permit) is True
    # The refused call's coroutine was closed, so collecting it does not report it unawaited.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        del outcome, error
        gc.collect()
    assert [f"{w.category.__name__}: {w.message}" for w in caught] == []


def test_close_on_the_client_thread_raises_instead_of_deadlocking(permit: SyncPermit) -> None:
    check(permit)

    outcome = run_on_client_thread(permit, permit.close)

    with pytest.raises(RuntimeError, match="own event loop thread"):
        outcome.result(timeout=5)
    assert check(permit) is True


class RecordingPermit(SyncPermit):
    """A sync client that records the thread on which its HTTP sessions are closed.

    A wait_for_sync() copy shares the list, and records nothing: it closes no sessions.
    """

    closed_on: list[str]

    async def _close_sessions(self) -> None:
        await super()._close_sessions()
        if self._owns_sessions:
            self.closed_on.append(threading.current_thread().name)


def recording_client(url: str) -> RecordingPermit:
    client = RecordingPermit(offline_config(url))
    client.closed_on = []
    return client


def test_close_closes_the_sessions_once_on_the_client_thread_while_a_copy_is_alive(
    config: PermitConfig, httpserver: HTTPServer
) -> None:
    """A wait_for_sync() copy shares its client's sessions, so they are closed once."""
    httpserver.expect_request("/allowed").respond_with_json({"allow": True})
    config.proxy_facts_via_pdp = True
    client = RecordingPermit(config)
    client.closed_on = []
    with client.wait_for_sync() as waiting:
        check(waiting)
        client.close()

    assert client.closed_on == [LOOP_THREAD_NAME]


class FailingPermit(SyncPermit):
    """A sync client whose HTTP sessions fail to close."""

    async def _close_sessions(self) -> None:
        await super()._close_sessions()
        msg = "the sessions did not close"
        raise OSError(msg)


def test_close_raises_what_closing_the_sessions_raised_and_still_stops(
    server: KeepAliveServer,
) -> None:
    client = FailingPermit(offline_config(server.url))
    check(client)
    thread = loop_thread(client)

    with pytest.raises(OSError, match="the sessions did not close"):
        client.close()

    assert thread is not None
    assert not thread.is_alive()
    assert loop_thread(client) is None


def test_close_without_a_call_closes_no_sessions(server: KeepAliveServer) -> None:
    client = recording_client(server.url)

    client.close()

    assert client.closed_on == []


# --- a client that is never closed -----------------------------------------------------


def test_a_client_that_is_garbage_collected_stops_its_thread(
    server: KeepAliveServer,
) -> None:
    client = SyncPermit(offline_config(server.url))
    check(client)
    thread = loop_thread(client)

    del client
    gc.collect()

    assert thread is not None
    wait_until_stopped(thread)
    assert not thread.is_alive()
    assert server.wait_until_closed(1) == 1


def test_an_api_object_outliving_its_client_keeps_working() -> None:
    with KeepAliveServer() as server:
        server.respond("/local/role_assignments", [])
        role_assignments = SyncPermit(offline_config(server.url)).pdp_api.role_assignments
        gc.collect()

        assert role_assignments.list(user_key="u") == []
        background_loop = _background_loop_of(role_assignments)
        assert background_loop is not None
        running = background_loop._thread
        assert running is not None

        del role_assignments, background_loop
        gc.collect()
        wait_until_stopped(running.thread)
        assert not running.thread.is_alive()


def test_a_client_freed_by_the_cycle_collector_closes_its_connection_without_a_warning(
    server: KeepAliveServer,
) -> None:
    """A client held in a reference cycle, as an exception it raised can hold it, is freed by gc.

    The client's sessions must not be collected with it while they are open, or aiohttp
    reports them unclosed.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = SyncPermit(offline_config(server.url))
        check(client)
        thread = loop_thread(client)
        cycle: list[object] = [client]
        cycle.append(cycle)
        del client, cycle
        gc.collect()
        assert thread is not None
        wait_until_stopped(thread)
        gc.collect()

    assert [f"{w.category.__name__}: {w.message}" for w in caught] == []
    assert not thread.is_alive()
    assert server.wait_until_closed(1) == 1


def test_a_client_never_closed_issues_no_warning(server: KeepAliveServer) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = SyncPermit(offline_config(server.url))
        check(client)
        thread = loop_thread(client)
        del client
        gc.collect()
        assert thread is not None
        wait_until_stopped(thread)
        gc.collect()

    assert [f"{w.category.__name__}: {w.message}" for w in caught] == []


def run_script(script: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    """Run `script` in a new interpreter that turns every warning into an error."""
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("PYTHONWARNINGS", "PYTHONDEVMODE")
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-W",
            "ignore:Support for pydantic 1 is deprecated:DeprecationWarning",
            "-c",
            script,
        ],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


SCRIPT_HEADER = """\
import atexit
import threading

from loguru import logger

from tests.keepalive_server import KeepAliveServer

logger.disable("permit")
server = KeepAliveServer()
server.start()


def report() -> None:
    opened = server.opened
    print("connections closed:", server.wait_until_closed(opened) == opened)
    loop_threads = [t for t in threading.enumerate() if t.name == "permit-sync-loop"]
    print("loop threads left:", len(loop_threads))


# Registered before permit is imported, so it runs after permit's own exit hook.
atexit.register(report)

from permit.sync import Permit
from tests.utils import offline_config


class Client(Permit):
    async def _close_sessions(self) -> None:
        await super()._close_sessions()
        print("sessions closed on", threading.current_thread().name)


client = Client(offline_config(server.url))
"""
AT_EXIT = "sessions closed on permit-sync-loop\nconnections closed: True\nloop threads left: 0\n"


def test_a_client_never_closed_is_closed_at_exit_without_noise() -> None:
    result = run_script(SCRIPT_HEADER + "print(client.check('user', 'read', 'document'))\n")

    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "True\n" + AT_EXIT


def test_a_call_in_flight_does_not_hold_up_the_exit() -> None:
    script = SCRIPT_HEADER + (
        "server.respond('/allowed', {'allow': True}, delay=60)\n"
        "def call():\n"
        "    try:\n"
        "        client.check('user', 'read', 'document')\n"
        "    except BaseException:\n"
        "        pass\n"
        "threading.Thread(target=call, daemon=True).start()\n"
        "print('in flight:', server.wait_for_requests(1))\n"
    )
    started = time.monotonic()

    result = run_script(script, timeout=30)

    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "in flight: True\n" + AT_EXIT
    assert time.monotonic() - started < 30


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_ctrl_c_while_waiting_cancels_the_call() -> None:
    script = """\
import asyncio
import os
import signal
import threading

from permit.utils.sync import SyncClass, _BackgroundLoop

started = threading.Event()
cancelled = threading.Event()


class Api(metaclass=SyncClass):
    async def wait(self) -> None:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise


def interrupt() -> None:
    started.wait(10)
    os.kill(os.getpid(), signal.SIGINT)


# A process started with SIGINT ignored, as a shell's background job is, inherits that.
signal.signal(signal.SIGINT, signal.default_int_handler)
background_loop = _BackgroundLoop()
api = Api()
background_loop.bind(api)
threading.Thread(target=interrupt).start()
try:
    api.wait()
except KeyboardInterrupt:
    print("interrupted")
print("cancelled:", cancelled.wait(10))
background_loop.close()
"""
    result = run_script(script, timeout=30)

    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "interrupted\ncancelled: True\n"


@pytest.mark.skipif(sys.platform == "win32", reason="os.fork")
def test_a_forked_child_starts_a_thread_of_its_own_and_closes_it() -> None:
    """The child leaves the parent's loop and connections alone, so close() cannot hang on them."""
    script = SCRIPT_HEADER + (
        "import os\n"
        "import sys\n"
        "import warnings\n"
        "print('parent:', client.check('user', 'read', 'document'), flush=True)\n"
        "# Python 3.12+ warns that forking a process that runs threads can deadlock the child.\n"
        "warnings.simplefilter('ignore', DeprecationWarning)\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    # The server's thread runs in the parent only.\n"
        "    atexit.unregister(report)\n"
        "    print('child:', client.check('user', 'read', 'document'), flush=True)\n"
        "    client.close()\n"
        "    print('child:', client.check('user', 'read', 'document'), flush=True)\n"
        "    sys.exit(0)\n"
        "_, status = os.waitpid(pid, 0)\n"
        "print('child exit status:', status)\n"
    )

    result = run_script(script, timeout=30)

    assert (result.returncode, result.stderr) == (0, "")
    closed_in_the_child = "sessions closed on permit-sync-loop\n"
    assert result.stdout == (
        "parent: True\n"
        f"child: True\n{closed_in_the_child}"
        f"child: True\n{closed_in_the_child}"
        "child exit status: 0\n" + AT_EXIT
    )


@pytest.mark.skipif(sys.platform == "win32", reason="os.fork")
def test_a_child_forked_while_close_runs_starts_a_thread_of_its_own() -> None:
    """The close() the parent runs does not run in the child, so a call must not wait for it."""
    script = SCRIPT_HEADER + (
        "import os\n"
        "import sys\n"
        "import time\n"
        "import warnings\n"
        "server.respond('/allowed', {'allow': True}, delay=1)\n"
        "threading.Thread(target=client.check, args=('user', 'read', 'document')).start()\n"
        "server.wait_for_requests(1)\n"
        "closing = threading.Thread(target=client.close)\n"
        "closing.start()\n"
        "while client._background_loop._closing is None:\n"
        "    time.sleep(0.01)\n"
        "# Python 3.12+ warns that forking a process that runs threads can deadlock the child.\n"
        "warnings.simplefilter('ignore', DeprecationWarning)\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    # The server's thread runs in the parent only.\n"
        "    atexit.unregister(report)\n"
        "    print('child:', client.check('user', 'read', 'document'), flush=True)\n"
        "    client.close()\n"
        "    sys.exit(0)\n"
        "_, status = os.waitpid(pid, 0)\n"
        "closing.join()\n"
        "print('child exit status:', status)\n"
    )

    result = run_script(script, timeout=30)

    assert (result.returncode, result.stderr) == (0, "")
    assert "child: True\n" in result.stdout
    assert "child exit status: 0\n" in result.stdout


# --- the background loop on its own ----------------------------------------------------

request_id: ContextVar[str] = ContextVar("request_id", default="<unset>")


class Probe(metaclass=SyncClass):
    """A blocking API object for the tests of the background loop itself."""

    async def request_id(self) -> str:
        return request_id.get()

    async def thread(self) -> threading.Thread:
        return threading.current_thread()

    @deprecated("old_fetch() is deprecated")
    async def old_fetch(self) -> None:
        await asyncio.sleep(0)


def blocking(method: Callable[[], object]) -> object:
    """Call a method of `Probe`, whose methods mypy sees as returning coroutines."""
    return method()


@pytest.fixture
def probe() -> Iterator[Probe]:
    background_loop = _BackgroundLoop()
    bound = Probe()
    background_loop.bind(bound)
    yield bound
    background_loop.close()


def test_close_cancels_the_tasks_a_call_left_running() -> None:
    left_running: list[asyncio.Task[None]] = []
    cancelled = threading.Event()

    async def linger() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    class Spawner(metaclass=SyncClass):
        async def spawn(self) -> None:
            left_running.append(asyncio.get_running_loop().create_task(linger()))
            await asyncio.sleep(0)

    background_loop = _BackgroundLoop()
    spawner = Spawner()
    background_loop.bind(spawner)
    blocking(spawner.spawn)

    background_loop.close()

    assert cancelled.is_set()
    assert left_running[0].cancelled()


def test_a_session_close_handed_to_the_loop_as_it_stops_still_closes_the_session(
    server: KeepAliveServer,
) -> None:
    """The loop cancels that close as it settles; shutting down its async generators closes it."""
    loop_thread = _LoopThread()
    sessions = LoopSessions()

    async def open_a_connection(through: LoopSessions) -> None:
        session = await through.current()
        async with session.post(f"{server.url}/allowed") as response:
            await response.read()

    opening = open_a_connection(sessions)
    asyncio.run_coroutine_threadsafe(opening, loop_thread.loop).result(timeout=5)
    del opening
    stopped, release = threading.Event(), threading.Event()

    def stop_and_hold() -> None:
        # The loop leaves run_forever() once this callback returns.
        loop_thread.loop.stop()
        stopped.set()
        release.wait(timeout=5)

    loop_thread.loop.call_soon_threadsafe(stop_and_hold)
    assert stopped.wait(timeout=5)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Collecting the sessions hands the close of the open one to the stopping loop.
        del sessions
        release.set()
        loop_thread.thread.join(timeout=5)
        gc.collect()

    assert not loop_thread.thread.is_alive()
    assert loop_thread.loop.is_closed()
    assert server.wait_until_closed(1) == 1
    assert [f"{w.category.__name__}: {w.message}" for w in caught] == []


def test_an_object_bound_to_no_client_runs_each_call_in_a_loop_of_its_own() -> None:
    unbound = Probe()

    first, second = blocking(unbound.thread), blocking(unbound.thread)

    assert first is threading.current_thread()
    assert second is threading.current_thread()


def test_the_caller_context_reaches_the_call(probe: Probe) -> None:
    token = request_id.set("r-1")
    try:
        inside = blocking(probe.request_id)
    finally:
        request_id.reset(token)

    assert inside == "r-1"
    assert blocking(probe.request_id) == "<unset>"


def test_concurrent_calls_each_warn_at_their_own_line(probe: Probe) -> None:
    both_calling = threading.Barrier(2)

    def first_caller() -> None:
        both_calling.wait(timeout=10)
        _ = probe.old_fetch()  # Blocking; mypy sees the async def it converts.

    def second_caller() -> None:
        both_calling.wait(timeout=10)
        _ = probe.old_fetch()  # Blocking; mypy sees the async def it converts.

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with ThreadPoolExecutor(max_workers=2) as executor:
            for future in [executor.submit(first_caller), executor.submit(second_caller)]:
                future.result()

    def call_line(function: Callable[..., object]) -> tuple[str, int]:
        return function.__code__.co_filename, function.__code__.co_firstlineno + 2

    assert sorted((w.filename, w.lineno) for w in caught) == sorted(
        [call_line(first_caller), call_line(second_caller)]
    )


def test_a_deprecated_method_of_the_client_warns_at_the_caller(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_oneshot_request(f"{FACTS}/users/u").respond_with_json(user_payload("u"))
    with SyncPermit(config) as client, warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        line = sys._getframe().f_lineno + 1
        client.api.get_user("u")

    assert [(w.category, w.filename, w.lineno) for w in caught] == [
        (DeprecationWarning, __file__, line)
    ]


# --- connection reuse ------------------------------------------------------------------


def test_sequential_calls_reuse_one_connection(permit: SyncPermit, server: KeepAliveServer) -> None:
    for _ in range(20):
        check(permit)

    assert (server.opened, server.closed) == (1, 0)


def test_concurrent_threads_open_at_most_one_connection_each(
    permit: SyncPermit, server: KeepAliveServer
) -> None:
    threads = 8
    all_started = threading.Barrier(threads)

    def caller(_: int) -> None:
        all_started.wait(timeout=10)
        for _call in range(10):
            check(permit)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        list(executor.map(caller, range(threads)))

    assert len(server.requests) == threads * 10
    assert server.opened <= threads
