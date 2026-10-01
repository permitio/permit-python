"""Offline tests of how the async client reuses and closes its HTTP connections (PER-16344).

The client sends its requests through one aiohttp session, with its pool of open
connections, for the Permit API and one for the PDP, per event loop. The connection tests
count connections at a local server that keeps them open between requests, as the Permit
API and the PDP do.
"""

import asyncio
import gc
import warnings
import weakref
from collections.abc import Callable, Coroutine, Iterator
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

USERS_PAGE = {"data": [], "total_count": 0, "page_count": 0}


@pytest.fixture
def server() -> Iterator[KeepAliveServer]:
    server = KeepAliveServer()
    server.start()
    yield server
    server.stop()


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


def test_a_client_does_not_keep_a_finished_loop_alive(server: KeepAliveServer) -> None:
    client = Permit(offline_config(server.url))
    loops: list[weakref.ref[asyncio.AbstractEventLoop]] = []

    async def remember_the_loop_and_check() -> bool:
        loops.append(weakref.ref(asyncio.get_running_loop()))
        return await check(client)

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
