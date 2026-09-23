import asyncio
import functools
import inspect
from collections.abc import Awaitable, Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from functools import wraps
from typing import Any, TypeGuard, TypeVar, cast

from typing_extensions import ParamSpec

P = ParamSpec("P")
T = TypeVar("T")

SYNC_WRAPPER_MARKER = "__permit_sync_wrapper__"
"""Attribute set on every wrapper produced by :func:`async_to_sync`.

It marks a callable as "already converted", which makes the conversion done by
:class:`SyncClass` idempotent and keeps :func:`iscoroutine_func` from walking
into the coroutine function such a wrapper consumes.
"""

_driving_coroutine: ContextVar[bool] = ContextVar("permit_driving_coroutine", default=False)
"""True while :func:`run_coroutine_sync` is driving a coroutine in this context."""


def _run_in_new_event_loop(coroutine: Coroutine[Any, Any, T]) -> T:
    token = _driving_coroutine.set(True)
    try:
        return asyncio.run(coroutine)
    finally:
        _driving_coroutine.reset(token)


def run_coroutine_sync(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run `coroutine` to completion and return its result.

    Args:
        coroutine: The coroutine to run.

    Returns:
        Whatever the coroutine returns.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_in_new_event_loop(coroutine)

    # This thread already drives a running event loop, which cannot be reused:
    # `loop.run_until_complete()` refuses to re-enter it and scheduling onto it
    # from here would deadlock, since we have to block until the result is in.
    # A dedicated thread with an event loop of its own is the only way out.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="permit-sync") as executor:
        return executor.submit(_run_in_new_event_loop, coroutine).result()


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
        if _driving_coroutine.get():
            return func(*args, **kwargs)  # type: ignore[return-value] # the driver awaits it
        return run_coroutine_sync(func(*args, **kwargs))

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
