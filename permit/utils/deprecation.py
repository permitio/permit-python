from collections.abc import Callable
from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, TypeVar, cast
from warnings import warn

from permit.utils.sync import _blocking_call_site

_F = TypeVar("_F", bound=Callable[..., Any])


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
            call_site = _blocking_call_site.get()
            if call_site is None:
                warn(message, DeprecationWarning, stacklevel=2)
            else:
                # The blocking client runs this coroutine under asyncio, so stacklevel would
                # blame asyncio's frames rather than the line that called the blocking method.
                call_site.warn(message, DeprecationWarning)
            return await func(*args, **kwargs)

        # Either wrapper takes and returns what func does, so callers keep func's type.
        if iscoroutinefunction(func):
            return cast("_F", async_wrapper)
        return cast("_F", wrapper)

    return decorator
