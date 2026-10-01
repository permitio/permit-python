from collections.abc import Callable
from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, TypeVar, cast
from warnings import warn

from permit.utils.sync import _blocking_call_site

_F = TypeVar("_F", bound=Callable[..., Any])


def _warn_deprecated(message: str) -> None:
    """Issue a `DeprecationWarning` attributed to the line that called the caller's caller.

    Call it from a coroutine function's body, so the warning names the line that awaited
    that coroutine function, or the line that made the blocking call that runs it.

    Args:
        message: The warning text, typically naming the replacement.
    """
    call_site = _blocking_call_site.get()
    if call_site is None:
        warn(message, DeprecationWarning, stacklevel=3)
    else:
        # The blocking client runs the coroutine under asyncio, so stacklevel would
        # blame asyncio's frames rather than the line that called the blocking method.
        call_site.warn(message, DeprecationWarning)


def deprecated(message: str) -> Callable[[_F], _F]:
    """Mark a function or coroutine function as deprecated.

    Every call emits a `DeprecationWarning` attributed to the caller.

    Args:
        message: The warning text, typically naming the replacement.

    Returns:
        A decorator that keeps the decorated function's signature.
    """

    def decorator(func: _F) -> _F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> object:
            warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> object:
            _warn_deprecated(message)
            return await func(*args, **kwargs)

        # Either wrapper takes and returns what func does, so callers keep func's type.
        if iscoroutinefunction(func):
            return cast("_F", async_wrapper)
        return cast("_F", wrapper)

    return decorator
