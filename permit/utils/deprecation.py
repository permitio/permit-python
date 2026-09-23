from asyncio import iscoroutinefunction
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar, cast
from warnings import warn

from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


def deprecated(message: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function or coroutine function as deprecated.

    Every call emits a `DeprecationWarning` attributed to the caller.

    Args:
        message: The warning text, typically naming the replacement.

    Returns:
        A decorator that keeps the decorated function's signature.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        async_func = cast("Callable[P, Awaitable[object]]", func)

        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
            warn(message, DeprecationWarning, stacklevel=2)
            return await async_func(*args, **kwargs)

        if iscoroutinefunction(func):
            return cast("Callable[P, R]", async_wrapper)
        return wrapper

    return decorator
