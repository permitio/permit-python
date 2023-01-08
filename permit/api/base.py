from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, Optional, TypeVar

from typing_extensions import ParamSpec

from permit.config import ApiKeyLevel, ContextFactory
from permit.constants import DEFAULT_TENANT_KEY
from permit.exceptions.exceptions import raise_for_error
from permit.openapi.api.api_keys import get_api_key_scope
from permit.utils.api_key import get_api_key_level

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
            self._logger.info("loading scope propertied from api in order to create a context")
            res = await get_api_key_scope.asyncio(client=self._client)
            raise_for_error(res, message="could not get api key scope in order to create a context")
            self._logger.info("got scope response from api")
            api_key_level = get_api_key_level(res)
            self._config.context = ContextFactory.build(project=res.project_id.hex, environment=res.environment_id.hex,
                                                        tenant=DEFAULT_TENANT_KEY, api_key_level=api_key_level)

        else:
            self._logger.debug("context is already loaded, skipping context loading")
        return await func(self, *args, **kwargs)

    return wrapper
