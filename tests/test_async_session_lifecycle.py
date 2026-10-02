"""Offline tests of how the async client reuses and closes its HTTP connections (PER-16344).

The client sends its requests through one aiohttp session, with its pool of open
connections, for the Permit API and one for the PDP, per event loop. The connection tests
count connections at a local server that keeps them open between requests, as the Permit
API and the PDP do.
"""

import asyncio
import gc
import os
import subprocess
import sys
import textwrap
import threading
import time
import warnings
import weakref
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from pytest_httpserver import HTTPServer
from yarl import URL

from permit import Permit, PermitConfig
from permit.api.base import BasePermitApi, SimpleHttpClient
from permit.pdp_api.base import BasePdpPermitApi
from permit.sync import Permit as SyncPermit
from permit.utils.http_sessions import LoopSessions
from tests.keepalive_server import KeepAliveServer, ServedRequest
from tests.utils import FACTS, offline_config

REPO_ROOT = Path(__file__).resolve().parents[1]
USERS_PAGE = {"data": [], "total_count": 0, "page_count": 0}
# How long a test waits for a loop in another thread.
THREAD_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def server() -> Iterator[KeepAliveServer]:
    with KeepAliveServer() as server:
        yield server


@pytest.fixture
def client(server: KeepAliveServer) -> Permit:
    server.respond(f"{FACTS}/users", USERS_PAGE)
    return Permit(offline_config(server.url))


def header(request: ServedRequest, name: str) -> str | None:
    """The value of the request's header ``name``, matched case-insensitively."""
    return next(
        (value for key, value in request.headers.items() if key.lower() == name.lower()), None
    )


async def check(client: Permit) -> bool:
    return await client.check("user-1", "read", "document")


# --- connection reuse ---------------------------------------------------------


async def test_sequential_checks_share_one_connection(
    server: KeepAliveServer, client: Permit
) -> None:
    for _ in range(5):
        assert await check(client)

    assert (len(server.requests), server.opened) == (5, 1)


async def test_the_api_calls_share_one_connection_and_the_pdp_calls_another(
    server: KeepAliveServer, client: Permit
) -> None:
    server.respond("/allowed/bulk", {"allow": [{"allow": True}]})
    server.respond("/user-permissions", {})
    server.respond("/user-tenants", [])
    server.respond("/local/role_assignments", [])
    server.respond("/v2/auth/elements_login_as", {"redirect_url": "http://elements.test/login"})
    server.respond(f"{FACTS}/tenants", [])

    assert await check(client)
    assert await client.bulk_check([{"user": "user-1", "action": "read", "resource": "doc"}])
    await client.get_user_permissions("user-1")
    await client.get_user_tenants("user-1")
    await client.pdp_api.role_assignments.list()
    pdp_connections = server.opened
    await client.api.users.list()
    await client.api.tenants.list()
    await client.elements.login_as("user-1", "tenant-1")

    assert (len(server.requests), pdp_connections, server.opened) == (8, 1, 2)


@pytest.mark.parametrize(
    "client_class", [pytest.param(Permit, id="async"), pytest.param(SyncPermit, id="sync")]
)
def test_every_api_of_a_client_sends_through_the_client_sessions(
    client_class: type[Permit],
) -> None:
    """Each of the client's APIs, and each API they hold, uses the client's sessions."""
    config = offline_config("http://localhost:1")
    config.proxy_facts_via_pdp = True
    client = client_class(config)

    with client.wait_for_sync() as waiting:
        for each in (client, waiting):
            api = sessions_reachable_from(each._api) | sessions_reachable_from(each._elements)
            pdp = sessions_reachable_from(each._enforcer) | sessions_reachable_from(each._pdp_api)
            assert api == {id(client._api_sessions)}
            assert pdp == {id(client._pdp_sessions)}


def sessions_reachable_from(root: object) -> set[int]:
    """The ids of the ``LoopSessions`` that ``root`` and every API and client it holds use."""
    found: set[int] = set()
    pending = [root]
    while pending:
        holder = pending.pop()
        for value in vars(holder).values():
            if isinstance(value, LoopSessions):
                found.add(id(value))
            elif isinstance(value, (BasePermitApi, BasePdpPermitApi, SimpleHttpClient)):
                pending.append(value)
    return found


async def test_a_request_replaces_a_session_closed_under_the_client(
    server: KeepAliveServer, client: Permit
) -> None:
    """A request never goes through a closed session.

    close() keeps the session of a loop that stopped before closing it, and the close handed
    to that loop closes it once the loop runs again.
    """
    assert await check(client)
    await (await client._pdp_sessions.current()).close()

    assert await check(client)
    assert server.opened == 2


async def test_the_connections_are_not_capped_in_number(client: Permit) -> None:
    """As when every request had a session of its own, any number may be open at once."""
    session = await client._pdp_sessions.current()

    assert session.connector is not None
    assert session.connector.limit == 0


async def test_a_cookie_the_server_sets_is_not_sent_back(server: KeepAliveServer) -> None:
    """The shared session keeps no cookies, so each request carries the headers it did alone."""
    server.respond("/allowed", {"allow": True}, headers={"Set-Cookie": "balancer=a1; Path=/"})
    # By a host name: aiohttp's cookie jar ignores cookies from an IP address.
    client = Permit(offline_config(server.url.replace("127.0.0.1", "localhost")))

    assert await check(client)
    assert await check(client)

    assert [header(request, "Cookie") for request in server.requests] == [None, None]


# --- event loops ---------------------------------------------------------------


def test_one_client_serves_two_successive_asyncio_runs(server: KeepAliveServer) -> None:
    client = Permit(offline_config(server.url))

    async def three_checks() -> list[bool]:
        return [await check(client) for _ in range(3)]

    assert asyncio.run(three_checks()) == [True] * 3
    # asyncio.run() closed the connection as it shut its loop down, without close().
    assert server.wait_until_closed(1) == 1
    assert asyncio.run(three_checks()) == [True] * 3
    assert server.wait_until_closed(2) == 2
    assert server.opened == 2


@pytest.mark.parametrize("close", [False, True], ids=["left open", "closed"])
def test_a_client_does_not_keep_a_finished_loop_alive(
    server: KeepAliveServer, *, close: bool
) -> None:
    client = Permit(offline_config(server.url))
    loops: list[weakref.ref[asyncio.AbstractEventLoop]] = []

    async def remember_the_loop_and_check() -> bool:
        loops.append(weakref.ref(asyncio.get_running_loop()))
        allowed = await check(client)
        if close:
            await client.close()
        return allowed

    assert asyncio.run(remember_the_loop_and_check())
    gc.collect()

    assert loops[0]() is None
    assert asyncio.run(check(client))


async def test_a_client_dropped_without_close_closes_its_connection(
    server: KeepAliveServer,
) -> None:
    """Dropping the last reference to a client closes its connections on their loop."""
    client = Permit(offline_config(server.url))
    assert await check(client)

    # Reference counting alone must free the client: nothing may hold it in a cycle.
    gc.disable()
    try:
        del client
        # Waits in another thread, so that this loop runs the close it was given.
        assert await asyncio.to_thread(server.wait_until_closed, 1) == 1
    finally:
        gc.enable()


async def test_a_client_freed_by_the_cycle_collector_closes_its_connection_without_a_warning(
    server: KeepAliveServer,
) -> None:
    """A client held in a reference cycle, as an exception it raised can hold it, is freed by gc.

    The client's sessions must not be collected with it while they are open, or aiohttp
    reports them unclosed.
    """
    client = Permit(offline_config(server.url))
    assert await check(client)
    cycle: list[object] = [client]
    cycle.append(cycle)
    del client, cycle

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        gc.collect()
        # Waits in another thread, so that this loop runs the close it was given.
        assert await asyncio.to_thread(server.wait_until_closed, 1) == 1

    assert [f"{w.category.__name__}: {w.message}" for w in caught] == []


def assert_nothing_reported_unclosed(drop: Callable[[], None]) -> None:
    """Run ``drop`` and a garbage collection, and check aiohttp reported nothing unclosed."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        drop()
        gc.collect()
    assert [str(warning.message) for warning in caught] == []


def run_on_a_loop_closed_without_shutting_down(coroutine: Coroutine[Any, Any, bool]) -> bool:
    """Run ``coroutine`` the old way: on a new loop, closed without shutting down its generators."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


# pytest-httpserver closes each connection after its response, so the closed loops in these
# tests keep no connection open, only their session.


def test_the_next_request_closes_the_session_of_a_loop_closed_without_shutting_down(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    client = Permit(config)
    assert run_on_a_loop_closed_without_shutting_down(check(client))

    assert asyncio.run(check(client))

    def drop() -> None:
        nonlocal client
        del client

    assert_nothing_reported_unclosed(drop)


# --- per-request settings ------------------------------------------------------


async def call_check(client: Permit) -> object:
    return await check(client)


async def call_pdp_api(client: Permit) -> object:
    return await client.pdp_api.role_assignments.list()


async def call_api(client: Permit) -> object:
    return await client.api.users.list()


@pytest.mark.parametrize(
    ("timeout_setting", "path", "call"),
    [
        ("pdp_timeout", "/allowed", call_check),
        ("pdp_timeout", "/local/role_assignments", call_pdp_api),
        ("api_timeout", f"{FACTS}/users", call_api),
    ],
    ids=["check", "pdp_api", "api"],
)
async def test_a_request_slower_than_its_timeout_fails(
    server: KeepAliveServer,
    timeout_setting: str,
    path: str,
    call: Callable[[Permit], Coroutine[Any, Any, object]],
) -> None:
    """Each request carries the client's timeout, now that the sessions are shared."""
    server.respond(path, [], delay=1.5)
    config = offline_config(server.url)
    setattr(config, timeout_setting, 1)
    client = Permit(config)

    with pytest.raises(asyncio.TimeoutError):
        await call(client)


async def test_headers_given_to_a_request_go_over_the_client_headers(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(f"{FACTS}/users", method="GET").respond_with_json(USERS_PAGE)
    client = SimpleHttpClient(
        {
            "base_url": httpserver.url_for("/"),
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer a"},
        },
        base_url=FACTS,
    )

    await client.get("/users", model=dict, headers={"authorization": "Bearer b", "X-Extra": "1"})

    [(request, _)] = httpserver.log
    sent = {
        name: request.headers.get(name) for name in ("Content-Type", "Authorization", "X-Extra")
    }
    assert sent == {"Content-Type": "application/json", "Authorization": "Bearer b", "X-Extra": "1"}


def test_a_client_config_option_requests_cannot_carry_is_refused() -> None:
    with pytest.raises(TypeError, match=r"\['cookies'\]"):
        SimpleHttpClient({"headers": {}, "cookies": {"session": "a"}})


BASE_URLS = [
    "http://pdp.test",
    "http://pdp.test/",
    "http://pdp.test:7766/prefix/",
    URL("http://pdp.test/prefix/"),
    "http://pdp.test/prefix",
    URL("http://pdp.test/prefix"),
    "pdp.test:7766",
    "//pdp.test/",
    "",
]
PATHS = ["/v2/facts/users", "v2/facts/users", "", "http://elsewhere.test/v2/x"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("base_url", BASE_URLS, ids=repr)
async def test_a_request_url_resolves_as_a_session_base_url_resolved_it(
    base_url: str | URL, path: str
) -> None:
    """The base URL moved from the session to each request without changing where it goes."""

    async def through_a_session() -> URL:
        async with aiohttp.ClientSession(base_url=base_url) as session:
            return session._build_url(path)

    async def through_the_client() -> URL:
        return SimpleHttpClient({"base_url": base_url})._request_url(path)

    assert await outcome(through_the_client) == await outcome(through_a_session)


async def outcome(resolve: Callable[[], Coroutine[Any, Any, URL]]) -> URL | tuple[type, str]:
    """What ``resolve`` returns, or the type and message of what it raises."""
    try:
        return await resolve()
    except ValueError as error:
        return type(error), str(error)


# --- close() and the context manager -------------------------------------------


async def test_close_closes_the_connections(server: KeepAliveServer, client: Permit) -> None:
    assert await check(client)
    await client.api.users.list()

    await client.close()

    assert server.wait_until_closed(2) == 2


async def test_async_with_yields_the_client_and_closes_it_on_exit(
    server: KeepAliveServer,
) -> None:
    client = Permit(offline_config(server.url))

    async with client as entered:
        assert entered is client
        assert await check(client)

    assert server.wait_until_closed(1) == 1


async def test_async_with_closes_the_client_when_the_block_raises(
    server: KeepAliveServer,
) -> None:
    async def check_then_fail() -> None:
        async with Permit(offline_config(server.url)) as client:
            assert await check(client)
            raise LookupError

    with pytest.raises(LookupError):
        await check_then_fail()

    assert server.wait_until_closed(1) == 1


async def test_closing_twice_closes_nothing_more(server: KeepAliveServer, client: Permit) -> None:
    assert await check(client)

    await client.close()
    await client.close()

    assert server.wait_until_closed(1) == 1
    assert server.opened == 1


async def test_close_on_a_client_that_sent_nothing_does_nothing(server: KeepAliveServer) -> None:
    await Permit(offline_config(server.url)).close()

    assert (server.opened, server.closed) == (0, 0)


async def test_a_request_after_close_opens_a_new_connection(
    server: KeepAliveServer, client: Permit
) -> None:
    assert await check(client)
    await client.close()

    assert await check(client)
    assert await check(client)

    assert server.opened == 2
    assert server.wait_until_closed(1) == 1
    await client.close()
    assert server.wait_until_closed(2) == 2


async def test_a_wait_for_sync_copy_shares_the_connection_and_leaves_closing_it_to_its_client(
    server: KeepAliveServer,
) -> None:
    config = offline_config(server.url)
    config.proxy_facts_via_pdp = True
    client = Permit(config)

    with client.wait_for_sync(timeout=3.0, policy="fail") as waiting:
        await waiting.api.tenants.delete("tenant-1")
        await waiting.close()
    await client.api.tenants.delete("tenant-2")

    waited, not_waited = server.requests
    assert (header(waited, "X-Wait-Timeout"), header(waited, "X-Timeout-Policy")) == ("3.0", "fail")
    assert (header(not_waited, "X-Wait-Timeout"), header(not_waited, "X-Timeout-Policy")) == (
        None,
        None,
    )
    # The copy's close() left the connection open: the client's request went over it.
    assert server.opened == 1

    await client.close()
    assert server.wait_until_closed(1) == 1
    # The copy still works after its client closed: it opens a new connection.
    await waiting.api.tenants.delete("tenant-3")
    assert server.opened == 2
    await client.close()
    assert server.wait_until_closed(2) == 2


async def test_without_proxy_facts_via_pdp_wait_for_sync_yields_the_client_itself(
    server: KeepAliveServer, client: Permit
) -> None:
    """So the yielded client's close() closes the connections, unlike a copy's."""
    assert not client.config.proxy_facts_via_pdp
    assert await check(client)

    with client.wait_for_sync() as waiting:
        assert waiting is client
        await waiting.close()

    assert server.wait_until_closed(1) == 1


async def test_close_also_closes_the_connection_of_a_loop_running_in_another_thread(
    server: KeepAliveServer, client: Permit
) -> None:
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        assert asyncio.run_coroutine_threadsafe(check(client), loop).result(THREAD_TIMEOUT_SECONDS)
        assert await check(client)
        assert server.opened == 2
        other_session = asyncio.run_coroutine_threadsafe(
            client._pdp_sessions.current(), loop
        ).result(THREAD_TIMEOUT_SECONDS)
        # Keep the other loop busy, so its session is closed only if close() waits for it.
        loop.call_soon_threadsafe(time.sleep, 0.2)

        await client.close()

        assert other_session.closed
        assert server.wait_until_closed(2) == 2
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(THREAD_TIMEOUT_SECONDS)
        loop.close()


def test_close_leaves_the_connection_of_an_idle_loop_to_that_loop(
    server: KeepAliveServer, client: Permit
) -> None:
    """A loop that is not running cannot close its session from another loop's close()."""
    idle = asyncio.new_event_loop()
    try:
        assert idle.run_until_complete(check(client))

        asyncio.run(client.close())
        # The idle loop's connection is still open: its next request goes over it.
        assert idle.run_until_complete(check(client))
        assert server.opened == 1

        idle.run_until_complete(client.close())
        assert server.wait_until_closed(1) == 1
    finally:
        idle.close()


def keep_the_loop_busy(busy: threading.Event, seconds: float = 0.5) -> None:
    """Block the running loop for ``seconds``, as a slow callback does: what it is handed waits."""
    busy.set()
    time.sleep(seconds)


async def test_close_returns_when_a_loop_in_another_thread_ends_before_closing_its_session(
    server: KeepAliveServer, client: Permit
) -> None:
    """That loop's asyncio.run() cancels the close handed to it, and closes the session itself."""
    assert await check(client)
    busy = threading.Event()

    async def check_then_end_busy() -> None:
        assert await check(client)
        keep_the_loop_busy(busy)

    other = threading.Thread(target=asyncio.run, args=(check_then_end_busy(),))
    other.start()
    try:
        assert await asyncio.to_thread(busy.wait, THREAD_TIMEOUT_SECONDS)
        await asyncio.wait_for(client.close(), THREAD_TIMEOUT_SECONDS)
    finally:
        await asyncio.to_thread(other.join, THREAD_TIMEOUT_SECONDS)

    assert await asyncio.to_thread(server.wait_until_closed, 2) == 2


async def test_close_returns_when_a_loop_in_another_thread_stops_before_closing_its_session(
    server: KeepAliveServer, client: Permit, caplog: pytest.LogCaptureFixture
) -> None:
    """The stopped loop closes the session as it shuts down its async generators."""
    assert await check(client)
    loop = asyncio.new_event_loop()

    def run_then_shut_down() -> None:
        loop.run_forever()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    other = threading.Thread(target=run_then_shut_down, daemon=True)
    other.start()
    busy = threading.Event()

    def stay_busy_then_stop() -> None:
        keep_the_loop_busy(busy)
        loop.stop()

    try:
        assert asyncio.run_coroutine_threadsafe(check(client), loop).result(THREAD_TIMEOUT_SECONDS)
        loop.call_soon_threadsafe(stay_busy_then_stop)
        assert await asyncio.to_thread(busy.wait, THREAD_TIMEOUT_SECONDS)
        await asyncio.wait_for(client.close(), THREAD_TIMEOUT_SECONDS)
    finally:
        await asyncio.to_thread(other.join, THREAD_TIMEOUT_SECONDS)

    assert loop.is_closed()
    assert await asyncio.to_thread(server.wait_until_closed, 2) == 2
    assert [record.getMessage() for record in caplog.records if record.name == "asyncio"] == []


def test_close_closes_every_other_session_when_one_loop_ends_before_closing_its_own(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    client = Permit(config)
    busy = threading.Event()

    async def check_then_end_busy() -> None:
        assert await check(client)
        keep_the_loop_busy(busy)

    # The session of the loop that ends first is the first the client opened.
    other = threading.Thread(target=asyncio.run, args=(check_then_end_busy(),))
    other.start()
    try:
        assert busy.wait(THREAD_TIMEOUT_SECONDS)
        assert run_on_a_loop_closed_without_shutting_down(check(client))
        asyncio.run(asyncio.wait_for(client.close(), THREAD_TIMEOUT_SECONDS))
    finally:
        other.join(THREAD_TIMEOUT_SECONDS)

    def drop() -> None:
        nonlocal client
        del client

    assert_nothing_reported_unclosed(drop)


def test_close_keeps_the_session_of_a_loop_that_stops_and_closes_before_closing_it(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """The next request marks it closed, as it does the session of any closed loop."""
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    client = Permit(config)
    loop = asyncio.new_event_loop()

    def run_then_close() -> None:
        loop.run_forever()
        loop.close()

    other = threading.Thread(target=run_then_close, daemon=True)
    busy = threading.Event()

    def stay_busy_then_stop() -> None:
        keep_the_loop_busy(busy)
        loop.stop()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        other.start()
        assert asyncio.run_coroutine_threadsafe(check(client), loop).result(THREAD_TIMEOUT_SECONDS)
        loop.call_soon_threadsafe(stay_busy_then_stop)
        assert busy.wait(THREAD_TIMEOUT_SECONDS)

        asyncio.run(asyncio.wait_for(client.close(), THREAD_TIMEOUT_SECONDS))
        other.join(THREAD_TIMEOUT_SECONDS)
        gc.collect()
        assert asyncio.run(check(client))
        del client
        gc.collect()

    assert loop.is_closed()
    assert [f"{w.category.__name__}: {w.message}" for w in caught] == []


def test_close_still_closes_the_other_sessions_when_one_fails_to_close(
    httpserver: HTTPServer, config: PermitConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The session that failed to close is kept, and the next close() closes it."""
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    client = Permit(config)
    # The first session the client opens is the one that fails to close. Its loop closes
    # only once the other session is open: opening a session closes those of closed loops.
    closed_later = asyncio.new_event_loop()
    assert closed_later.run_until_complete(check(client))
    [failing] = [entry.session for entry in client._pdp_sessions._sessions.values()]
    close_session = aiohttp.ClientSession.close

    async def close_or_fail(session: aiohttp.ClientSession) -> None:
        if session is failing:
            msg = "the session did not close"
            raise OSError(msg)
        await close_session(session)

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        assert asyncio.run_coroutine_threadsafe(check(client), loop).result(THREAD_TIMEOUT_SECONDS)
        other = asyncio.run_coroutine_threadsafe(client._pdp_sessions.current(), loop).result(
            THREAD_TIMEOUT_SECONDS
        )
        closed_later.close()
        monkeypatch.setattr(aiohttp.ClientSession, "close", close_or_fail)

        with pytest.raises(OSError, match="the session did not close"):
            asyncio.run(client.close())

        assert other.closed
        assert not failing.closed
        monkeypatch.undo()
        asyncio.run(client.close())
        assert failing.closed
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(THREAD_TIMEOUT_SECONDS)
        loop.close()
        closed_later.close()


def test_a_loop_closed_without_shutting_down_leaves_its_connection_to_the_garbage_collector(
    server: KeepAliveServer, client: Permit
) -> None:
    """The documented limit of a loop closed with ``loop.close()`` alone.

    Nothing can close a connection on a closed loop, so it stays open until the next request
    marks the session closed and the garbage collector frees the connection, which Python
    reports with a ResourceWarning. Running close() on the loop before closing it closes the
    connection instead (test_close_leaves_the_connection_of_an_idle_loop_to_that_loop).
    """
    assert run_on_a_loop_closed_without_shutting_down(check(client))
    assert server.wait_until_closed(1, timeout=0.2) == 0

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert asyncio.run(check(client))
        gc.collect()

    assert caught
    assert {warning.category for warning in caught} == {ResourceWarning}
    assert all("unclosed" in str(warning.message) for warning in caught)
    # The connection of the closed loop, and the one asyncio.run() closed as it ended.
    assert server.wait_until_closed(2) == 2


def test_close_closes_the_session_of_a_loop_closed_without_shutting_down(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    client = Permit(config)
    assert run_on_a_loop_closed_without_shutting_down(check(client))

    asyncio.run(client.close())

    def drop() -> None:
        nonlocal client
        del client

    assert_nothing_reported_unclosed(drop)


def test_a_close_handed_to_a_loop_that_closes_first_leaves_nothing_unawaited(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """A client collected on its running loop hands it the close, and the loop may stop first."""
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    client = Permit(config)
    loop = asyncio.new_event_loop()
    assert loop.run_until_complete(check(client))

    def drop_and_stop() -> None:
        nonlocal client
        del client
        loop.stop()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loop.call_soon(drop_and_stop)
        loop.run_forever()
        loop.close()
        gc.collect()
        # The next request marks the session of the closed loop closed.
        assert asyncio.run(check(Permit(config)))
        gc.collect()

    assert [f"{w.category.__name__}: {w.message}" for w in caught] == []


def test_a_client_dropped_after_its_loop_closed_without_shutting_down_reports_nothing(
    httpserver: HTTPServer, config: PermitConfig
) -> None:
    """Its session is kept until the next request, from any client, marks it closed."""
    httpserver.expect_request("/allowed", method="POST").respond_with_json({"allow": True})
    client = Permit(config)
    assert run_on_a_loop_closed_without_shutting_down(check(client))
    [entry] = client._pdp_sessions._sessions.values()
    session = weakref.ref(entry.session)
    del entry

    def drop() -> None:
        nonlocal client
        del client

    assert_nothing_reported_unclosed(drop)
    assert session() is not None

    assert asyncio.run(check(Permit(config)))
    gc.collect()

    assert session() is None


EXIT_SCRIPT = """
import asyncio
import sys
import threading

from permit import Permit

client = Permit(token="test-token", pdp=sys.argv[1], api_url=sys.argv[1])
loop = asyncio.new_event_loop()
check = client.check("user-1", "read", "document")
{use}
print("checked")
"""

EXIT_SCENARIOS = {
    "a loop still running in a daemon thread": """
threading.Thread(target=loop.run_forever, daemon=True).start()
assert asyncio.run_coroutine_threadsafe(check, loop).result(5)
""",
    "a loop that is not running": """
assert loop.run_until_complete(check)
""",
    "a loop closed without shutting down": """
assert loop.run_until_complete(check)
loop.close()
""",
    "a client dropped after its loop closed without shutting down": """
assert loop.run_until_complete(check)
loop.close()
del check, client
""",
}


@pytest.mark.parametrize("use", EXIT_SCENARIOS.values(), ids=EXIT_SCENARIOS.keys())
def test_a_client_never_closed_reports_nothing_unclosed_at_exit(
    server: KeepAliveServer, use: str
) -> None:
    """The interpreter's exit closes the sessions whose loop it finds still open.

    The script runs under Python's default warning filters, as an application does: they
    hide ResourceWarnings, but not what aiohttp logs about a session it finds unclosed.
    """
    script = EXIT_SCRIPT.format(use=textwrap.dedent(use))
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("PYTHONWARNINGS", "PYTHONDEVMODE")
    }

    result = subprocess.run(
        [sys.executable, "-c", script, server.url],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert (result.returncode, result.stdout) == (0, "checked\n"), result.stderr
    reported = [
        line
        for line in result.stderr.splitlines()
        if "nclosed" in line or "Exception ignored" in line
    ]
    assert reported == []


FORK_SCRIPT = """
import asyncio
import os
import sys
import threading
import warnings

from permit import Permit

client = Permit(token="test-token", pdp=sys.argv[1], api_url=sys.argv[1])
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
check = client.check("user-1", "read", "document")
assert asyncio.run_coroutine_threadsafe(check, loop).result(5)
# Python 3.12+ warns that forking a process that runs threads can deadlock the child.
warnings.simplefilter("ignore", DeprecationWarning)
pid = os.fork()
if pid == 0:
    print("child:", asyncio.run(client.check("user-1", "read", "document")), flush=True)
    asyncio.run(client.close())
    print("child closed", flush=True)
    sys.exit(0)
_, status = os.waitpid(pid, 0)
print("child exit status:", status)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="os.fork")
def test_a_forked_child_leaves_the_parent_sessions_alone(server: KeepAliveServer) -> None:
    """The parent's loop does not run in the child, so close() must not wait for it there."""
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("PYTHONWARNINGS", "PYTHONDEVMODE")
    }

    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "ignore:Support for pydantic 1 is deprecated:DeprecationWarning",
            "-c",
            FORK_SCRIPT,
            server.url,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "child: True\nchild closed\nchild exit status: 0\n"
    # The parent's connection and the child's, which the child's asyncio.run() closed.
    assert server.opened == 2
