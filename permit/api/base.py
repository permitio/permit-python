from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, Optional, TypeVar

from typing_extensions import ParamSpec

from permit.config import ApiKeyLevel, ContextFactory, get_api_key_level
from permit.constants import DEFAULT_TENANT_KEY
from permit.exceptions.exceptions import raise_for_error
from permit.openapi.api.api_keys import get_api_key_scope

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


def lazy_load_context(func: Callable[P, RT]) -> Callable[P, Awaitable[RT]]:
    async def wrapper(self: PermitBaseApi, *args: P.args, **kwargs: P.kwargs) -> RT:
        if self._config.context is None:
            self._config.context = await ContextFactory.build(
                client=self._client,
            )

        else:
            self._logger.debug("context is already loaded, skipping context loading")
        return await func(self, *args, **kwargs)

    return wrapper
