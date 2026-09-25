import asyncio
import functools
import inspect
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from functools import wraps
from types import FrameType
from typing import Any, Awaitable, Callable, Coroutine, Dict, NamedTuple, Optional, Set, Type, TypeVar, cast

from typing_extensions import ParamSpec, TypeGuard

P = ParamSpec("P")
T = TypeVar("T")

SYNC_WRAPPER_MARKER = "__permit_sync_wrapper__"
"""Attribute set on every wrapper produced by :func:`async_to_sync`.

It marks a callable as "already converted", which makes the conversion done by
:class:`SyncClass` idempotent and keeps :func:`iscoroutine_func` from walking
into the coroutine function such a wrapper consumes.
"""


class CallSite(NamedTuple):
    """The line that called a blocking method, as `warnings.warn` records a frame."""

    filename: str
    lineno: int
    module_globals: Dict[str, Any]

    @classmethod
    def from_frame(cls, frame: Optional[FrameType]) -> "CallSite":
        """The line `frame` is running, or, with no frame, the place `warnings.warn` blames then.

        There is no frame when C code calls the blocking method directly, as it does an
        atexit hook or a function started with `_thread.start_new_thread`.
        """
        if frame is None:
            return cls("<sys>", 0, sys.__dict__)
        return cls(frame.f_code.co_filename, frame.f_lineno, frame.f_globals)

    def warn(self, message: str, category: Type[Warning]) -> None:
        """Issue a warning attributed to this line, exactly as `warnings.warn` would from its frame.

        The module name and the once-per-line registry come from the calling module, as
        `warnings.warn` takes them, so filters that match on the module (such as Python's
        default `default::DeprecationWarning:__main__`) and the `default` action behave the same.

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
            module_globals=self.module_globals,
        )


_blocking_call_site: ContextVar[Optional[CallSite]] = ContextVar("permit_blocking_call_site", default=None)
"""Set while :func:`run_coroutine_sync` drives a coroutine in this context: where the blocking call was made."""


def blocking_call_site() -> Optional[CallSite]:
    """The line that called the blocking method whose coroutine is running.

    Returns:
        Where the blocking method was called, when the current coroutine runs on its behalf,
        otherwise None. Code in that coroutine can use it to attribute a warning to the
        caller: the coroutine runs under asyncio, whose frames stand between it and the call.
    """
    return _blocking_call_site.get()


def _run_in_new_event_loop(coroutine: Coroutine[Any, Any, T], call_site: CallSite) -> T:
    token = _blocking_call_site.set(call_site)
    try:
        return asyncio.run(coroutine)
    finally:
        _blocking_call_site.reset(token)


def run_coroutine_sync(coroutine: Coroutine[Any, Any, T], call_site: CallSite) -> T:
    """Run `coroutine` to completion and return its result.

    Args:
        coroutine: The coroutine to run.
        call_site: The line that called the blocking method `coroutine` runs for. The
            coroutine sees it through :func:`blocking_call_site`, even when it runs in
            another thread.

    Returns:
        Whatever the coroutine returns.
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


def async_to_sync(func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, T]:
    """Turn an async callable into a blocking one.

    Args:
        func: The coroutine function to convert.

    Returns:
        A callable that runs `func` to completion and returns its result. When it
        is called from inside a coroutine that `run_coroutine_sync` is already
        driving, the coroutine is handed back untouched instead, so that internal
        `await self.public_method(...)` calls keep working on a converted class.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        if blocking_call_site() is not None:
            return func(*args, **kwargs)  # type: ignore[return-value]
        # Read in the caller's thread, while its frame is the one that called us.
        call_site = CallSite.from_frame(sys._getframe(0).f_back)
        return run_coroutine_sync(func(*args, **kwargs), call_site)

    setattr(wrapper, SYNC_WRAPPER_MARKER, True)
    return wrapper


def iscoroutine_func(callable: Callable) -> TypeGuard[Callable[..., Awaitable]]:
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
    candidate: Optional[Any] = callable
    seen: Set[int] = set()
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

    def __new__(cls, name, bases, class_dict):
        class_obj = super().__new__(cls, name, bases, class_dict)

        for attr_name in dir(class_obj):
            if attr_name.startswith("_"):
                # do not monkey-patch protected or private methods
                continue

            attr = getattr(class_obj, attr_name, None)
            if not callable(attr) or not iscoroutine_func(attr):
                continue

            # monkey-patch public async method using the async_to_sync decorator
            coroutine_function = cast(Callable[..., Coroutine[Any, Any, Any]], attr)
            setattr(class_obj, attr_name, async_to_sync(coroutine_function))

        return class_obj
