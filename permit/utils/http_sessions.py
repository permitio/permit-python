import asyncio
import atexit
import concurrent.futures
import contextlib
import functools
import os
import sys
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
      ``close()`` does not leave it open;
    - as the interpreter exits, if its loop is still open then: on that loop if it is not
      running, or by that loop's thread if it runs in another thread;
    - once this object is garbage collected, on its loop if that loop is running. Until
      then, and until the session is closed, a finalizer holds it apart from this object:
      the garbage collector never finds an open session unreachable, so aiohttp never
      reports one unclosed, even when the client that holds this object ends up in a
      reference cycle.

    A child process made by ``fork()`` sets the sessions it inherits aside, untouched: their
    loops cannot run in the child, and their connections are the parent's. The child's
    requests open sessions of their own.

    The sessions carry no headers, base URL or timeout: each request brings its own, so one
    session serves every request sent from its loop. They keep no cookies either, so a
    request carries exactly the headers it would carry through a session of its own.

    Every API object, HTTP client and enforcer builds one of these for itself, so that it
    works when used alone. A ``Permit`` client then gives all of them its own two, one for
    the Permit API and one for the PDP, through their ``_use_sessions()``: the ones they
    built open no session, and are collected right away.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Changed in place only: the finalizer holds this dict.
        self._sessions: dict[asyncio.AbstractEventLoop, _LoopSession] = {}
        _open_at_exit.add(self)
        finalizer = weakref.finalize(self, _orphan, self._sessions)
        # Writable, as the weakref documentation says; typeshed declares __slots__ = () on
        # it. At exit, the exit hook below closes the sessions of the objects still alive.
        finalizer.atexit = False  # type: ignore[misc]

    async def current(self) -> aiohttp.ClientSession:
        """The session of the running event loop, created by the first call from that loop.

        Returns:
            The session to send the request through.
        """
        loop = asyncio.get_running_loop()
        with self._lock:
            existing = self._sessions.get(loop)
            # A session close() kept, because its loop stopped first, may be closing now.
            if existing is not None and not existing.session.closed:
                return existing.session
            abandoned = self._take_sessions_of_closed_loops() + _take_orphans_of_closed_loops()
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
        waits for it while that loop runs. A loop that stops before it has closed its
        session, or that is neither running nor closed, cannot run anything now: its session
        stays open until that loop shuts down its async generators, or ``close()`` runs on
        it. A request in flight on a session being closed fails.

        The sessions are closed side by side: when one fails to close, the others are still
        closed, and the first error is raised then. A session that is still open afterwards,
        including when the task running this is cancelled, is kept for the next ``close()``.
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
        try:
            outcomes = await asyncio.gather(
                *(_close_from(running, loop, entry) for loop, entry in closable.items()),
                return_exceptions=True,
            )
        finally:
            for loop, entry in closable.items():
                self._keep_if_open(loop, entry)
        # Errors only: gather has raised the cancellation of this task already.
        errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if errors:
            raise errors[0]

    def _keep_if_open(self, loop: asyncio.AbstractEventLoop, entry: _LoopSession) -> None:
        """Keep ``entry``, which ``close()`` took, if its session is still open."""
        with self._lock:
            if entry.session.closed:
                return
            if loop in self._sessions:
                # The loop opened a new session meanwhile: keep this one apart, for its loop
                # to close when it shuts down its async generators.
                _orphaned[id(entry.session)] = (loop, entry)
            else:
                self._sessions[loop] = entry

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

    def _set_aside_after_fork(self) -> None:
        """In a child made by ``fork()``: keep the inherited sessions, but never use them.

        Only the thread that forked runs in the child, so the lock may be held by a thread
        that is gone, and no loop of the parent runs. Closing an inherited session would
        close connections the parent still uses, so they stay open, and referenced, for the
        life of the child.
        """
        self._lock = threading.Lock()
        _sessions_lost_to_fork.extend(self._sessions.values())
        self._sessions.clear()

    def _close_at_exit(self) -> None:
        """Close every session as the interpreter exits, from a thread that runs no loop."""
        with self._lock:
            entries = list(self._sessions.items())
            self._sessions.clear()
        of_closed_loops = [
            entry.session for loop, entry in entries if not _close_at_exit_on(loop, entry)
        ]
        if of_closed_loops:
            # The connections of a closed loop cannot be closed, but its sessions can be
            # marked closed from any loop, which keeps aiohttp from reporting them unclosed.
            asyncio.run(_close_all(of_closed_loops))


async def _close_with_loop(
    sessions: weakref.ref[LoopSessions],
    loop: asyncio.AbstractEventLoop,
    session: aiohttp.ClientSession,
) -> AsyncGenerator[None, None]:
    """An async generator that closes ``session`` when it is closed.

    It holds ``sessions`` weakly, so that a client dropped without ``close()`` is garbage
    collected.
    """
    try:
        yield
    finally:
        owner = sessions()
        if owner is not None:
            owner._forget(loop, session)  # noqa: SLF001 - this module's own class
        try:
            await session.close()
        finally:
            _orphaned.pop(id(session), None)


async def _close_all(sessions: list[aiohttp.ClientSession]) -> None:
    for session in sessions:
        await session.close()


async def _close_from(
    running: asyncio.AbstractEventLoop, loop: asyncio.AbstractEventLoop, entry: _LoopSession
) -> None:
    """Close ``entry``, the session of ``loop``, from the ``running`` loop."""
    if loop is running:
        await entry.closer.aclose()
        return
    closing = None if loop.is_closed() else _hand_close_to(loop, entry)
    if closing is None:
        # Nothing touches the closed loop: its connections cannot be closed any more, and
        # this only marks the session closed.
        await entry.session.close()
        return
    await _wait_while_running(loop, closing)
    # Not done, or cancelled: the loop stopped first, and closes the session as it shuts
    # down its async generators.
    if closing.done() and not closing.cancelled():
        error = closing.exception()
        if error is not None:
            raise error


def _hand_close_to(
    loop: asyncio.AbstractEventLoop, entry: _LoopSession
) -> concurrent.futures.Future[None] | None:
    """Start closing ``entry`` on ``loop``, from another thread; None if ``loop`` is closed.

    The coroutine is created on the loop: one the loop never runs, because it closes first,
    would be reported as never awaited.

    Returns:
        The future of the close, which is cancelled if the loop cancels the close.
    """
    closing: concurrent.futures.Future[None] = concurrent.futures.Future()
    try:
        loop.call_soon_threadsafe(_start_closing_task, loop, entry, closing)
    except RuntimeError:  # the loop is closed
        return None
    return closing


def _start_closing_task(
    loop: asyncio.AbstractEventLoop,
    entry: _LoopSession,
    closing: concurrent.futures.Future[None],
) -> None:
    task = loop.create_task(_close_on_its_loop(entry))
    # The loop holds its tasks weakly: this keeps the task until it is done.
    _closing_tasks.add(task)
    task.add_done_callback(_closing_tasks.discard)
    task.add_done_callback(functools.partial(_report_close, closing))


async def _close_on_its_loop(entry: _LoopSession) -> None:
    """Close the session, then its closer.

    In this order, a loop that shuts down its async generators while the session closes
    finds the session closed already, rather than its closer running.
    """
    await entry.session.close()
    await entry.closer.aclose()


def _report_close(closing: concurrent.futures.Future[None], task: asyncio.Task[None]) -> None:
    """Give ``closing`` the outcome of ``task``, the close it stands for."""
    if task.cancelled():
        closing.cancel()
    elif (error := task.exception()) is not None:
        closing.set_exception(error)
    else:
        closing.set_result(None)


async def _wait_while_running(
    loop: asyncio.AbstractEventLoop, closing: concurrent.futures.Future[None]
) -> None:
    """Wait until ``closing`` is done, or until ``loop``, which runs it, stops running."""
    here = asyncio.get_running_loop()
    done = asyncio.Event()

    def wake(_: concurrent.futures.Future[None]) -> None:
        with contextlib.suppress(RuntimeError):  # this loop closed meanwhile
            here.call_soon_threadsafe(done.set)

    closing.add_done_callback(wake)
    while not done.is_set() and loop.is_running():
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(done.wait(), _STOPPED_LOOP_POLL_SECONDS)


def _close_at_exit_on(loop: asyncio.AbstractEventLoop, entry: _LoopSession) -> bool:
    """Close ``entry`` on ``loop`` as the interpreter exits; False if ``loop`` is closed.

    A loop running in another thread gets the close to run, and is not waited for: its
    thread, if it is a daemon, may be stopped first, which leaves nothing to report.
    """
    if loop.is_closed():
        return False
    if loop.is_running():
        return _hand_close_to(loop, entry) is not None
    loop.run_until_complete(entry.closer.aclose())
    return True


def _orphan(sessions: dict[asyncio.AbstractEventLoop, _LoopSession]) -> None:
    """Keep the sessions of a collected `LoopSessions` until they are closed.

    The session of a running loop is closed on that loop now; the session of a loop that is
    not running is closed when that loop shuts down its async generators; one of a closed
    loop is marked closed by the next request from any loop. As a finalizer, this may run
    in any thread, so it only hands the closes to the loops.
    """
    entries = list(sessions.items())
    sessions.clear()
    for loop, entry in entries:
        _orphaned[id(entry.session)] = (loop, entry)
        if loop.is_running():
            _hand_close_to(loop, entry)


def _take_orphans_of_closed_loops() -> list[_LoopSession]:
    """Remove and return the orphaned sessions of loops closed without shutting them down."""
    taken = []
    for key, (loop, entry) in list(_orphaned.items()):
        if loop.is_closed() and _orphaned.pop(key, None) is not None:
            taken.append(entry)
    return taken


_open_at_exit: weakref.WeakSet[LoopSessions] = weakref.WeakSet()
# The open sessions no LoopSessions holds any more, by the id of the session: those of
# collected LoopSessions, and those close() kept while their loop had a new one.
_orphaned: dict[int, tuple[asyncio.AbstractEventLoop, _LoopSession]] = {}
_closing_tasks: set[asyncio.Task[None]] = set()
# How often close() looks whether a loop it waits for in another thread still runs.
_STOPPED_LOOP_POLL_SECONDS = 0.05
_sessions_lost_to_fork: list[_LoopSession] = []


@atexit.register
def _close_open_sessions_at_exit() -> None:
    for sessions in list(_open_at_exit):
        sessions._close_at_exit()  # noqa: SLF001 - this module's own class


def _set_aside_sessions_after_fork() -> None:
    for sessions in list(_open_at_exit):
        sessions._set_aside_after_fork()  # noqa: SLF001 - this module's own class


if sys.platform != "win32":
    os.register_at_fork(after_in_child=_set_aside_sessions_after_fork)
