from asyncio import iscoroutinefunction
from functools import wraps
from warnings import warn


def deprecated(message: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            warn(message, DeprecationWarning, stacklevel=2)
            return await func(*args, **kwargs)

        if iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator
