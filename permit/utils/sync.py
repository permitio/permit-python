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


class SyncClass(type):
    def __new__(mcs, name, bases, class_dict):
        class_obj = super().__new__(mcs, name, bases, class_dict)

        for name in dir(class_obj):
            if name.startswith("_"):
                # do not monkey-patch protected or private method
                continue

            attr = getattr(class_obj, name)

            if callable(attr) and iscoroutine_func(attr):
                # monkey-patch public method using async_to_sync decorator
                setattr(class_obj, name, async_to_sync(attr))

        return class_obj
