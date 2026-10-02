import asyncio
import atexit
import concurrent.futures
import contextlib
import functools
import inspect
import os
import sys
import threading
import warnings
import weakref
from collections.abc import Awaitable, Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from functools import wraps
from types import FrameType
from typing import (
    Any,
    NamedTuple,
    TypeGuard,
    TypeVar,
    cast,
)

from typing_extensions import ParamSpec

from permit.utils.sdk_logger import sdk_logger

P = ParamSpec("P")
T = TypeVar("T")

CloseSessions = Callable[[], Coroutine[Any, Any, None]]
"""A coroutine function that closes the HTTP sessions of a sync client."""

SYNC_WRAPPER_MARKER = "__permit_sync_wrapper__"
"""Attribute set on every wrapper produced by :func:`async_to_sync`.

It marks a callable as "already converted", which makes the conversion done by
:class:`SyncClass` idempotent and keeps :func:`iscoroutine_func` from walking
into the coroutine function such a wrapper consumes.
"""


class _CallSite(NamedTuple):
    """The line that called a blocking method, as `warnings.warn` records a frame."""

    filename: str
    lineno: int
    module_globals: dict[str, Any]

    @classmethod
    def from_frame(cls, frame: FrameType | None) -> "_CallSite":
        """The line `frame` is running, or, with no frame, the place `warnings.warn` blames then.

        There is no frame when C code calls the blocking method directly, as it does an
        atexit hook or a function started with `_thread.start_new_thread`.
        """
        if frame is None:
            return cls("<sys>", 0, sys.__dict__)
        return cls(frame.f_code.co_filename, frame.f_lineno, frame.f_globals)

    def warn(self, message: str, category: type[Warning]) -> None:
        """Issue a warning attributed to this line, exactly as `warnings.warn` would from its frame.

        The module name and the once-per-line registry come from the calling module, as
        `warnings.warn` takes them, so filters that match on the module (such as Python's
        default `default::DeprecationWarning:__main__`) and the `default` action behave the same.
        Like `warnings.warn`, it does not pass the module's globals on: from Python 3.12, with
        them `warn_explicit` asks the module's loader for the source line, which issues a second
        warning for a script's `__main__` and raises for code run by `exec` or `runpy`.

        Args:
            message: The warning's text.
            category: The warning's class.
        """
        warnings.warn_explicit(
            message,
            category,
            self.filename,
            self.lineno,
            module=self.module_globals.get("__name__", "<string>"),
            registry=self.module_globals.setdefault("__warningregistry__", {}),
        )


_blocking_call_site: ContextVar[_CallSite | None] = ContextVar(
    "permit_blocking_call_site", default=None
)
"""The line that made the blocking call whose coroutine runs in this context, otherwise None.

The coroutine runs under asyncio, whose frames stand between it and that line, so code in it
reads this to attribute a warning to the caller.
"""


def _run_in_new_event_loop(coroutine: Coroutine[Any, Any, T], call_site: _CallSite) -> T:
    token = _blocking_call_site.set(call_site)
    try:
        return asyncio.run(coroutine)
    finally:
        _blocking_call_site.reset(token)


def _run_blocking(coroutine: Coroutine[Any, Any, T], call_site: _CallSite) -> T:
    """Run `coroutine` to completion for the blocking call made at `call_site`.

    The coroutine sees `call_site` in `_blocking_call_site`, even when it runs in another thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_in_new_event_loop(coroutine, call_site)

    # This thread already drives a running event loop, which cannot be reused:
    # `loop.run_until_complete()` refuses to re-enter it and scheduling onto it
    # from here would deadlock, since we have to block until the result is in.
    # A dedicated thread with an event loop of its own is the only way out.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="permit-sync") as executor:
        return executor.submit(_run_in_new_event_loop, coroutine, call_site).result()


def run_coroutine_sync(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run `coroutine` to completion and return its result.

    Args:
        coroutine: The coroutine to run. A method marked with `deprecated` that it awaits
            warns at the line that called this function.

    Returns:
        Whatever the coroutine returns.
    """
    caller = sys._getframe(0).f_back  # noqa: SLF001 - the documented way to read a caller's frame
    return _run_blocking(coroutine, _CallSite.from_frame(caller))


_CALL_ON_LOOP_THREAD = (
    "A blocking call of permit.sync.Permit was made on the client's own event loop thread "
    "({thread}), where it would wait for itself forever. Make the call from another thread, "
    "or await the async client, permit.Permit."
)
_CLOSE_ON_LOOP_THREAD = (
    "permit.sync.Permit.close() was called on the client's own event loop thread ({thread}), "
    "which close() stops and joins. Call it from another thread."
)

_BACKGROUND_LOOP_ATTRIBUTE = "_permit_background_loop"
"""The attribute through which an object of a `SyncClass` class reaches its client's loop.

`_BackgroundLoop.bind` sets it. A blocking method of an object without it runs its coroutine
in an event loop of its own, as every blocking call did before the sync client had a
background loop.
"""


class _Raised(NamedTuple):
    """The exception a blocking call's coroutine raised, carried to the caller as a result.

    `asyncio.run_coroutine_threadsafe` copies an exception into the caller's future through
    asyncio's own conversion, which on Python 3.11 and 3.12 replaces a `TimeoutError` with a
    new one that has neither its traceback nor its cause. As a result it is not converted, so
    the caller raises the exception the coroutine raised.
    """

    error: Exception


class _LoopThread:
    """An event loop that runs in a daemon thread until it is shut down.

    It tracks the tasks it runs for blocking calls, so that a shutdown can wait for them, or
    cancel them.
    """

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        # Read and written on the loop's thread only.
        self._tasks: set[asyncio.Task[Any]] = set()
        self._stopping: asyncio.Task[None] | None = None
        self.thread = threading.Thread(target=self._serve, name="permit-sync-loop", daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            self.loop.run_forever()
            self.loop.run_until_complete(self._settle())
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        finally:
            self.loop.close()

    async def _settle(self) -> None:
        """Finish the tasks still on the stopped loop: tracked ones run, any other is cancelled.

        Another task may be one that a call left running, or the close of an HTTP session
        that a finalizer handed to the loop as it stopped; shutting down the loop's async
        generators next closes any session such a close left open.
        """
        current = asyncio.current_task()
        while others := asyncio.all_tasks() - {current}:
            for task in others - self._tasks:
                task.cancel()
            await asyncio.wait(others)

    async def _track(self, coroutine: Coroutine[Any, Any, T], call_site: _CallSite) -> T | _Raised:
        """Await `coroutine` as a tracked task that runs for the blocking call made at `call_site`.

        The task runs in a copy of the context of the thread that submitted it, as
        `call_soon_threadsafe` documents, and `_blocking_call_site` is set in that copy.

        Returns:
            What the coroutine returns, or the exception it raises, as a `_Raised`. A
            cancellation, of the task or from the coroutine, is raised.
        """
        # Never None: this coroutine only ever runs as a task.
        task = cast("asyncio.Task[Any]", asyncio.current_task())
        self._tasks.add(task)
        try:
            _blocking_call_site.set(call_site)
            return await coroutine
        except Exception as error:  # noqa: BLE001 - the blocking caller raises it
            return _Raised(error)
        finally:
            self._tasks.discard(task)
            # An exception the coroutine raised keeps this frame in its traceback, and the
            # task keeps the exception: without this, the three form a cycle that holds the
            # coroutine's objects until the cyclic garbage collector runs.
            del task

    def submit(
        self, coroutine: Coroutine[Any, Any, T], call_site: _CallSite
    ) -> concurrent.futures.Future[T | _Raised]:
        """Start `coroutine` on the loop, for the blocking call made at `call_site`.

        Args:
            coroutine: The coroutine to run.
            call_site: The line that made the blocking call.

        Returns:
            The future of the coroutine's result, or of the exception it raised, as a
            `_Raised`.

        Raises:
            RuntimeError: If the loop is closed. `coroutine` is closed, never started.
        """
        tracked = self._track(coroutine, call_site)
        try:
            return asyncio.run_coroutine_threadsafe(tracked, self.loop)
        except BaseException:
            tracked.close()
            coroutine.close()
            raise

    async def drain(self, *, cancel: bool) -> None:
        """Wait until no tracked task is left, cancelling each one first when `cancel` is True."""
        current = asyncio.current_task()
        while pending := self._tasks - {current}:
            if cancel:
                for task in pending:
                    task.cancel()
            await asyncio.wait(pending)

    async def _drain_and_close(
        self, close_sessions: CloseSessions | None, *, cancel_calls: bool, call_site: _CallSite
    ) -> None:
        # The sessions' close() may await the client's own converted methods, which must hand
        # back their coroutines rather than block, as they do in any blocking call's coroutine.
        _blocking_call_site.set(call_site)
        await self.drain(cancel=cancel_calls)
        if close_sessions is not None:
            await close_sessions()

    def close(
        self, close_sessions: CloseSessions | None, *, cancel_calls: bool, call_site: _CallSite
    ) -> None:
        """Wait for (or cancel) the tracked tasks, run `close_sessions`, then stop and join.

        Args:
            close_sessions: The coroutine function that closes the sessions opened on this
                loop, if any.
            cancel_calls: Cancel the blocking calls in flight instead of waiting for them.
            call_site: The line that called close().
        """
        drained = self._drain_and_close(
            close_sessions, cancel_calls=cancel_calls, call_site=call_site
        )
        try:
            asyncio.run_coroutine_threadsafe(drained, self.loop).result()
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join()

    def stop_soon(self) -> None:
        """Stop the loop once its tracked tasks are done, without waiting; safe in a finalizer."""
        # A closed loop raises; there is nothing left to stop then.
        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self._start_stopping)

    def _start_stopping(self) -> None:
        self._stopping = self.loop.create_task(self._drain_and_stop())

    async def _drain_and_stop(self) -> None:
        await self.drain(cancel=False)
        self.loop.stop()


class _BackgroundLoop:
    """The event loop on which a sync client runs its blocking calls, in a daemon thread.

    The thread starts on the first call. Calls from any number of threads are submitted to
    it and waited for, so they share the client's HTTP sessions and connections. `close()`
    waits for the calls in flight, closes the sessions and stops the thread; the next call
    starts a new one. While a `close()` runs, a call or another `close()` from another
    thread waits for it to finish. A client that is never closed has its thread stopped
    once nothing references this object any more, or at interpreter exit.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Notified, with the lock held, when a close() finishes.
        self._closed = threading.Condition(self._lock)
        self._thread: _LoopThread | None = None
        # The thread a close() is stopping, until it has stopped.
        self._closing: _LoopThread | None = None
        self._stop_when_collected: weakref.finalize[[], _BackgroundLoop] | None = None
        self._closer: weakref.WeakMethod[CloseSessions] | None = None
        _background_loops.add(self)

    def bind(self, *roots: object) -> None:
        """Run the blocking calls of `roots`, and of every `SyncClass` object they hold, here.

        Args:
            roots: The objects a sync client exposes, such as its enforcer and API clients.
        """
        pending = list(roots)
        seen: set[int] = set()
        while pending:
            obj = pending.pop()
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            if isinstance(type(obj), SyncClass):
                setattr(obj, _BACKGROUND_LOOP_ATTRIBUTE, self)
            pending.extend(
                value for value in vars(obj).values() if isinstance(type(value), SyncClass)
            )

    def set_closer(self, close_sessions: "weakref.WeakMethod[CloseSessions]") -> None:
        """Run `close_sessions` on the loop when it is closed, while its client is alive.

        Args:
            close_sessions: A weak reference to the client's method that closes its sessions.
        """
        with self._lock:
            self._closer = close_sessions

    def run(self, coroutine: Coroutine[Any, Any, T], call_site: _CallSite) -> T:
        """Run `coroutine` on the loop for the blocking call made at `call_site`, and wait.

        Args:
            coroutine: The coroutine of the blocking call.
            call_site: The line that made the blocking call.

        Returns:
            Whatever the coroutine returns.

        Raises:
            RuntimeError: If called from the loop's own thread, where waiting would deadlock.
        """
        future: concurrent.futures.Future[T | _Raised] | None = None
        try:
            with self._lock:
                future = self._thread_for_call().submit(coroutine, call_site)
            outcome = future.result()
        except BaseException:
            if future is None:
                coroutine.close()
            raise
        finally:
            if future is not None:
                # A no-op once the call is done. When waiting was interrupted, such as by
                # KeyboardInterrupt, it cancels the call, as asyncio.run() would.
                future.cancel()
        if not isinstance(outcome, _Raised):
            return outcome
        error = outcome.error
        # The error's traceback will hold this frame: drop what would lead back to the error.
        del outcome, future
        try:
            raise error
        finally:
            del error

    def _thread_for_call(self) -> _LoopThread:
        """The loop thread to run a call on, started first if there is none.

        Called with the lock held. While a close() stops the thread, this waits for it, then
        starts a new one.

        Raises:
            RuntimeError: If the caller is the loop thread, or the one a close() is stopping,
                where waiting would deadlock.
        """
        while self._thread is None and self._closing is not None:
            self._refuse_on(self._closing, _CALL_ON_LOOP_THREAD)
            self._closed.wait()
        if self._thread is None:
            self._thread = _LoopThread()
            stop_when_collected = weakref.finalize(self, self._thread.stop_soon)
            # Only when collected: at exit, _close_running_loops closes the loop, with the
            # client's sessions. Writable, as the weakref documentation says; typeshed
            # declares __slots__ = () on it.
            stop_when_collected.atexit = False  # type: ignore[misc]
            self._stop_when_collected = stop_when_collected
            _running_loops.add(self)
        else:
            self._refuse_on(self._thread, _CALL_ON_LOOP_THREAD)
        return self._thread

    @staticmethod
    def _refuse_on(loop_thread: _LoopThread, message: str) -> None:
        """Raise RuntimeError with `message` if the caller runs on `loop_thread`."""
        if loop_thread.thread is threading.current_thread():
            raise RuntimeError(message.format(thread=loop_thread.thread.name))

    def close(self, *, cancel_calls: bool = False) -> None:
        """Close the sessions opened on the loop and stop its thread, if it is running.

        A close() that another thread runs is waited for first. So when this returns, the
        thread has stopped, unless a call started a new one since.

        Args:
            cancel_calls: Cancel the blocking calls in flight instead of waiting for them.

        Raises:
            RuntimeError: If called from the loop's own thread, which it would have to join.
        """
        caller = sys._getframe(0).f_back  # noqa: SLF001 - see run_coroutine_sync
        call_site = _CallSite.from_frame(caller)
        with self._lock:
            while self._closing is not None:
                self._refuse_on(self._closing, _CLOSE_ON_LOOP_THREAD)
                self._closed.wait()
            loop_thread = self._thread
            if loop_thread is None:
                return
            self._refuse_on(loop_thread, _CLOSE_ON_LOOP_THREAD)
            self._thread = None
            self._closing = loop_thread
            if self._stop_when_collected is not None:
                self._stop_when_collected.detach()
                self._stop_when_collected = None
            _running_loops.discard(self)
            close_sessions = None if self._closer is None else self._closer()
        try:
            loop_thread.close(close_sessions, cancel_calls=cancel_calls, call_site=call_site)
        finally:
            with self._lock:
                self._closing = None
                self._closed.notify_all()

    def forget_thread(self) -> None:
        """In a child process made by fork(): drop the thread, which the fork did not copy.

        The next call starts a new thread. The old loop is kept referenced, not closed: it
        still looks like it is running, so closing it would raise, and collecting it would
        report it, and the sessions bound to it, as unclosed.
        """
        self._lock = threading.Lock()
        self._closed = threading.Condition(self._lock)
        _loops_lost_to_fork.extend(
            lost for lost in (self._thread, self._closing) if lost is not None
        )
        self._thread = None
        self._closing = None
        if self._stop_when_collected is not None:
            self._stop_when_collected.detach()
            self._stop_when_collected = None


_running_loops: "weakref.WeakSet[_BackgroundLoop]" = weakref.WeakSet()
# Every background loop, including those a close() is stopping, which _running_loops leaves
# out so that the exit hook does not wait for them.
_background_loops: "weakref.WeakSet[_BackgroundLoop]" = weakref.WeakSet()
_loops_lost_to_fork: list[_LoopThread] = []


def _close_running_loops() -> None:
    """At interpreter exit, close every running background loop, with its client's sessions.

    The calls still in flight can only come from daemon threads by then, and are cancelled
    rather than waited for, so they cannot hold up the exit.
    """
    for background_loop in list(_running_loops):
        _close_at_exit(background_loop)


def _close_at_exit(background_loop: _BackgroundLoop) -> None:
    try:
        background_loop.close(cancel_calls=True)
    except Exception as error:  # noqa: BLE001 - logged; the other clients still get closed
        sdk_logger.error(f"Could not close a Permit sync client at exit: {error!r}")


def _forget_threads_after_fork() -> None:
    for background_loop in list(_background_loops):
        background_loop.forget_thread()
    _running_loops.clear()


atexit.register(_close_running_loops)
if sys.platform != "win32":
    os.register_at_fork(after_in_child=_forget_threads_after_fork)


def _background_loop_of(obj: object) -> _BackgroundLoop | None:
    """The background loop `obj` was bound to, if it was."""
    candidate = getattr(obj, _BACKGROUND_LOOP_ATTRIBUTE, None)
    return candidate if isinstance(candidate, _BackgroundLoop) else None


def async_to_sync(func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, T]:
    """Turn an async callable into a blocking one.

    Args:
        func: The coroutine function to convert.

    Returns:
        A callable that runs `func` to completion and returns its result: on the background
        loop of the sync client that the first argument (`self`, for a method) belongs to,
        otherwise in an event loop of its own. When it is called from inside a coroutine
        that a blocking call is already driving, the coroutine is handed back untouched
        instead, so that internal `await self.public_method(...)` calls keep working on a
        converted class.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        if _blocking_call_site.get() is not None:
            return func(*args, **kwargs)  # type: ignore[return-value]
        # Read in the caller's thread, while its frame is the one that called us.
        caller = sys._getframe(0).f_back  # noqa: SLF001 - see run_coroutine_sync
        call_site = _CallSite.from_frame(caller)
        background_loop = _background_loop_of(args[0]) if args else None
        coroutine = func(*args, **kwargs)
        if background_loop is None:
            return _run_blocking(coroutine, call_site)
        return background_loop.run(coroutine, call_site)

    setattr(wrapper, SYNC_WRAPPER_MARKER, True)
    return wrapper


def iscoroutine_func(
    callable: Callable[..., object],  # noqa: A002 - public parameter; renaming breaks keyword callers
) -> TypeGuard[Callable[..., Awaitable[object]]]:
    """Whether calling `callable` produces an awaitable.

    `inspect.iscoroutinefunction` on its own is not enough: a decorator may wrap
    an `async def` in a plain function that returns the inner coroutine (pydantic's
    `validate_arguments` does exactly that), so the chain of `functools.wraps`
    targets and `functools.partial` objects has to be walked. The walk stops at
    wrappers produced by `async_to_sync`, which consume the coroutine they wrap
    and therefore are not async themselves.

    Args:
        callable: The callable to inspect.

    Returns:
        True if calling it returns an awaitable.
    """
    candidate: object | None = callable
    seen: set[int] = set()
    while candidate is not None and id(candidate) not in seen:
        seen.add(id(candidate))
        if getattr(candidate, SYNC_WRAPPER_MARKER, False):
            return False
        if inspect.iscoroutinefunction(candidate):
            return True
        if isinstance(candidate, functools.partial):
            candidate = candidate.func
            continue
        candidate = getattr(candidate, "__wrapped__", None)
    return False


class SyncClass(type):
    """Metaclass that turns every public async method of a class into a blocking one.

    Conversion is idempotent: each generated wrapper carries `SYNC_WRAPPER_MARKER`,
    so a class whose base was already converted leaves the inherited methods alone
    instead of wrapping them a second time. Marking is used rather than converting
    only the attributes in the class body, because the SDK's sync classes have empty
    bodies - every method they expose is inherited from their async counterpart.
    """

    def __new__(cls, name: str, bases: tuple[type, ...], class_dict: dict[str, Any]) -> "SyncClass":
        """Create the class, then replace each public coroutine method with a blocking wrapper."""
        class_obj = super().__new__(cls, name, bases, class_dict)

        for attr_name in dir(class_obj):
            if attr_name.startswith("_"):
                # do not monkey-patch protected or private methods
                continue

            attr = getattr(class_obj, attr_name, None)
            if not callable(attr) or not iscoroutine_func(attr):
                continue

            # monkey-patch public async method using the async_to_sync decorator
            coroutine_function = cast("Callable[..., Coroutine[Any, Any, Any]]", attr)
            setattr(class_obj, attr_name, async_to_sync(coroutine_function))

        return class_obj
