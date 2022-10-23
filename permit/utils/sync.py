import asyncio
from asyncio import iscoroutinefunction
from functools import wraps
from typing import Awaitable, Callable, TypeVar

from typing_extensions import ParamSpec, TypeGuard

P = ParamSpec("P")
T = TypeVar("T")


def run_sync(callback: Awaitable[T]) -> T:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # there is no running event loop, so it's safe to use `asyncio.run`
        return asyncio.run(callback)
    else:
        # there *is* a running event loop, so use `loop.run_until_complete`
        return loop.run_until_complete(callback)


def async_to_sync(func: Callable[P, Awaitable[T]]) -> Callable[P, T]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return run_sync(func(*args, **kwargs))

    return wrapper


def iscoroutine_func(callable: Callable) -> TypeGuard[Callable[..., Awaitable]]:
    return iscoroutinefunction(callable)
