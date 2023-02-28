from __future__ import annotations

import functools
from _ast import arg
from functools import partial
from typing import TYPE_CHECKING, Awaitable, Callable, TypeVar

from typing_extensions import ParamSpec

from permit.config import ApiKeyLevel, ContextFactory
from permit.exceptions.exceptions import PermitContextError

if TYPE_CHECKING:
    from loguru import Logger

    from permit import PermitConfig

P = ParamSpec("P")
RT = TypeVar("RT")


class PermitBaseApi:
    def __init__(
        self,
        client,
        config: PermitConfig,
        logger: Logger,
    ):
        self._config = config
        self._client = client
        self._logger = logger
        self._api_key_level: ApiKeyLevel = ApiKeyLevel.WAIT_FOR_INIT


def lazy_load_context(
    func: Callable[P, RT] = None,
    call_level: ApiKeyLevel = ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY,
):
    assert callable(func) or func is None

    def decorator(func: Callable[P, RT]) -> Callable[P, Awaitable[RT]]:
        @functools.wraps(func)
        async def wrapper(self: PermitBaseApi, *args: P.args, **kwargs: P.kwargs) -> RT:
            if self._config.context is None:
                self._config.context = await ContextFactory.build(
                    client=self._client,
                )
            else:
                self._logger.debug(
                    "context is already loaded, skipping context loading"
                )
            if (
                call_level == ApiKeyLevel.PROJECT_LEVEL_API_KEY
                and not self._config.context.project
            ):
                raise PermitContextError(
                    """
                                            You're trying to use an SDK method that's specific to a project,
                                            but you haven't set the current project in your client's context yet,
                                            or you are using an organization level API key.
                                            Please set the context to a specific
                                            project using `permit.set_context()` method.
                                        """
                )
            if call_level == ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY and (
                not self._config.context.environment or not self._config.context.project
            ):
                raise PermitContextError(
                    """
                                            You're trying to use an SDK method that's specific to an environment,
                                            but you haven't set the current environment in your client's context yet,
                                            or you are using an organization/project level API key.
                                            Please set the context to a specific
                                            environment using `permit.set_context()` method.
                                        """
                )
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator(func) if callable(func) else decorator
