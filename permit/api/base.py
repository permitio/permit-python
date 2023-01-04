from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, Optional, TypeVar

from typing_extensions import ParamSpec

from permit.exceptions.exceptions import raise_for_error
from permit.openapi.api.api_keys import get_api_key_scope
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead

if TYPE_CHECKING:
    from loguru import Logger

    from permit import PermitConfig
    from permit.api.client import PermitApiClient

P = ParamSpec("P")
RT = TypeVar("RT")


class PermitBaseApi:
    def __init__(
        self,
        client,
        config: PermitConfig,
        scope: Optional[APIKeyScopeRead],
        logger: Logger,
    ):
        self._config = config
        self._scope: Optional[APIKeyScopeRead] = scope
        self._client = client
        self._logger = logger


def lazy_load_scope(func: Callable[P, RT]) -> Callable[P, Awaitable[RT]]:
    async def wrapper(self: PermitBaseApi, *args: P.args, **kwargs: P.kwargs) -> RT:
        if self._scope is None:
            self._logger.info("loading scope propertied from api")
            res = await get_api_key_scope.asyncio(client=self._client)
            raise_for_error(res, message="could not get api key scope")
            self._logger.info("got scope response from api")
            self._scope = res
        else:
            self._logger.debug("scope is already loaded, skipping scope loading")
        return await func(self, *args, **kwargs)

    return wrapper
