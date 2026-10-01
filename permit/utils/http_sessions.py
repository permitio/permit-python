import asyncio
import concurrent.futures
import threading
import weakref
from collections.abc import AsyncGenerator
from typing import NamedTuple

import aiohttp


class _LoopSession(NamedTuple):
    """A loop's session, and the async generator that closes it when the loop shuts down."""

    session: aiohttp.ClientSession
    closer: AsyncGenerator[None, None]


class LoopSessions:
    """The aiohttp sessions an SDK client sends its requests through, one per event loop.

    An aiohttp session, and the connections it keeps open for reuse, belong to the event
    loop that created them. So the client has one session per loop it is used on: a single
    one in an application that runs one loop, a new one for each ``asyncio.run()`` call.
    Each is created by the first request sent from its loop.

    A session is closed:

    - by ``close()``;
    - when its loop shuts down its async generators, as ``asyncio.run()`` and
      ``asyncio.Runner`` do before they close the loop, so a program that never calls
      ``close()`` does not leave it open.

    The sessions carry no headers, base URL or timeout: each request brings its own, so one
    session serves every request sent from its loop. They keep no cookies either, so a
    request carries exactly the headers it would carry through a session of its own.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[asyncio.AbstractEventLoop, _LoopSession] = {}

    async def current(self) -> aiohttp.ClientSession:
        """The session of the running event loop, created by the first call from that loop.

        Returns:
            The session to send the request through.
        """
        loop = asyncio.get_running_loop()
        with self._lock:
            existing = self._sessions.get(loop)
            if existing is not None:
                return existing.session
            abandoned = self._take_sessions_of_closed_loops()
            session = aiohttp.ClientSession(
                # No limit on concurrent connections, as when every request had a session of
                # its own; idle connections are kept open for the next request.
                connector=aiohttp.TCPConnector(limit=0),
                cookie_jar=aiohttp.DummyCookieJar(),
            )
            closer = _close_with_loop(weakref.ref(self), loop, session)
            self._sessions[loop] = _LoopSession(session, closer)
        # Runs the generator up to its `yield`, which registers it with the loop: the loop
        # closes it, and so the session, when it shuts down its async generators.
        await anext(closer)
        for stale in abandoned:
            await stale.session.close()
        return session

    async def close(self) -> None:
        """Close the sessions of every loop that can close them now.

        The session of the running loop, and those of loops already closed, are closed here.
        The session of a loop running in another thread is closed on that loop, and this
        waits for it. A loop that is neither running nor closed cannot run anything now: its
        session stays open until that loop shuts down its async generators, or ``close()``
        runs on it. A request in flight on a session being closed fails.
        """
        running = asyncio.get_running_loop()
        with self._lock:
            closable = {
                loop: entry
                for loop, entry in self._sessions.items()
                if loop is running or loop.is_closed() or loop.is_running()
            }
            for loop in closable:
                del self._sessions[loop]
        for loop, entry in closable.items():
            if loop is running:
                await entry.closer.aclose()
                continue
            closing = None if loop.is_closed() else _start_closing(loop, entry.closer)
            if closing is None:
                # Nothing touches the closed loop: its connections cannot be closed any
                # more, and this only marks the session closed.
                await entry.session.close()
            else:
                await asyncio.wrap_future(closing)

    def _forget(self, loop: asyncio.AbstractEventLoop, session: aiohttp.ClientSession) -> None:
        """Drop ``session`` from the sessions, if it is still the one of ``loop``."""
        with self._lock:
            entry = self._sessions.get(loop)
            if entry is not None and entry.session is session:
                del self._sessions[loop]

    def _take_sessions_of_closed_loops(self) -> list[_LoopSession]:
        """Remove and return the sessions of loops closed without shutting them down.

        The caller holds the lock.
        """
        closed = [loop for loop in self._sessions if loop.is_closed()]
        return [self._sessions.pop(loop) for loop in closed]


async def _close_with_loop(
    sessions: weakref.ref[LoopSessions],
    loop: asyncio.AbstractEventLoop,
    session: aiohttp.ClientSession,
) -> AsyncGenerator[None, None]:
    """An async generator that closes ``session`` when it is closed.

    It holds ``sessions`` weakly, so that a client dropped without ``close()`` is garbage
    collected; the event loop then closes this generator, and so the session.
    """
    try:
        yield
    finally:
        owner = sessions()
        if owner is not None:
            owner._forget(loop, session)  # noqa: SLF001 - this module's own class
        await session.close()


async def _aclose(closer: AsyncGenerator[None, None]) -> None:
    await closer.aclose()


def _start_closing(
    loop: asyncio.AbstractEventLoop, closer: AsyncGenerator[None, None]
) -> concurrent.futures.Future[None] | None:
    """Close ``closer`` on ``loop`` from another thread; None if ``loop`` is closed already."""
    closing = _aclose(closer)
    try:
        return asyncio.run_coroutine_threadsafe(closing, loop)
    except RuntimeError:
        closing.close()
        return None
