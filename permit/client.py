import json
from typing import Dict, List, Union

from loguru import logger

from permit.api.client import PermitApiClient
from permit.config import ConfigFactory, ContextFactory, PermitConfig, PermitContext
from permit.constants import DEFAULT_PDP_URL
from permit.enforcement.enforcer import Action, Enforcer, Resource, User
from permit.mutations.client import PermitApiClient as CompatApiClient
from permit.mutations.client import ReadOperation, WriteOperation
from permit.openapi.models import UserCreate, UserRead
from permit.resources.interfaces import (
    ActionConfig,
    OnUserCreation,
    ResourceConfig,
    ResourceTypes,
)
from permit.resources.registry import ActionDefinition, ResourceRegistry
from permit.resources.reporter import ResourceReporter, ResourceStub
from permit.utils.context import Context


class Permit:
    def __init__(
        self,
        token: str,
        pdp: str = DEFAULT_PDP_URL,
        context: PermitContext = None,
        debug_mode: bool = False,
        **options,
    ):
        self._config: PermitConfig = ConfigFactory.build(
            dict(
                token=token, pdp=pdp, debug_mode=debug_mode, context=context, **options
            ),
        )
        self._logger = logger.bind(name="permit.io")
        self._resource_registry = ResourceRegistry()
        self._resourece_reporter = ResourceReporter(
            self._config, self._resource_registry
        )
        self._enforcer = Enforcer(self._config)
        # TODO: self._cache = LocalCacheClient(self._config, logger)

        self._mutations_client = CompatApiClient(self._config)
        self._api_client = PermitApiClient(self._config, self._context)
        if self._config.debug_mode:
            self._logger.info(
                f"Permit.io SDK initialized with config:\n${json.dumps(self._config.dict())}",
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

    # TODO: Implement getAllowedActions - With given user and resource, what actions the user is permitted to do.
    # async def get_allowed_actions(
    #     self,
    #     user: User,
    #     action: Action,
    #     resource: Resource,
    #     context: Context = {},
    # ) -> bool:
    #     return True

    # resource reporter
    async def resource(self, config: ResourceConfig) -> ResourceStub:
        return await self._resource_reporter.resource(config)

    def action(self, config: ActionConfig) -> ActionDefinition:
        return self._resource_reporter.action(config)

    async def sync_resources(self, config: ResourceTypes) -> List[ResourceStub]:
        return await self._resource_reporter.sync_resources(config)

    # mutations
    @property
    def api(self):
        return self._api_client

    @property
    async def sync_user(self):
        return self._api_client.sync_user

    @property
    def elements(self):
        return self._api_client.elements

    async def read(self, *operations: ReadOperation) -> List[Dict]:
        return await self._mutations_client.read(*operations)

    async def write(self, *operations: WriteOperation) -> List[Dict]:
        return await self._mutations_client.write(*operations)
