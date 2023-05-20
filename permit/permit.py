import json
from typing import Dict, List, Optional

from loguru import logger

from permit.api.client import PermitApiClient
from permit.config import ConfigFactory, PermitConfig
from permit.api.elements import PermitElements
from permit.enforcement.enforcer import Action, Enforcer, Resource, User
from permit.utils.context import Context


class Permit:
    def __init__(self, *, config: Optional[PermitConfig] = None, **options):
        self._config: PermitConfig = config if config is not None else PermitConfig(**options)
        self._logger = logger.bind(name="permit.io")
        self._enforcer = Enforcer(self._config)
        # TODO: self._cache = LocalCacheClient(self._config, logger)

        self._api_client = PermitApiClient(self._config)

        self._elements = PermitElements(self)

        self._logger.debug(
            "Permit SDK initialized with config:\n${}",
            json.dumps(self._config.dict())
        )

    @property
    def config(self):
        return self._config.copy()

    # enforcer
    async def check(
        self,
        user: User,
        action: Action,
        resource: Resource,
        context: Context = {},
    ) -> bool:
        return await self._enforcer.check(user, action, resource, context)

    @property
    def elements(self):
        return self._elements

    # mutations
    @property
    def api(self):
        return self._api_client.api