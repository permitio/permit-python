import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")
AsyncFunc = Callable[..., Awaitable[T]]


def run_sync(callback: AsyncFunc[T]) -> T:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # there is no running event loop, so it's safe to use `asyncio.run`
        return asyncio.run(callback)
    else:
        # there *is* a running event loop, so use `loop.run_until_complete`
        return loop.run_until_complete(callback)
