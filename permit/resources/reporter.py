import json
from typing import List

import aiohttp
from loguru import logger
from pydantic import BaseModel

from permit.config import PermitConfig
from permit.resources.interfaces import ActionConfig, ResourceConfig, ResourceTypes
from permit.resources.registry import (
    ActionDefinition,
    ResourceDefinition,
    ResourceRegistry,
)


class SyncObjectResponse(BaseModel):
    id: str


class AbstractResourceReporter:
    def add_action_to_resource(self, resource_name: str, action_def: ActionDefinition):
        raise NotImplementedError("abstract class")


class ResourceStub:
    def __init__(self, reporter: AbstractResourceReporter, resource_name: str):
        self._reporter = reporter
        self._resource_name = resource_name

    def action(self, config: ActionConfig):
        action = ActionDefinition(
            name=config.name,
            title=config.title,
            description=config.description,
            path=config.path,
            attributes=config.attributes or {},
        )
        self._reporter.add_action_to_resource(self._resource_name, action)


class ResourceReporter(AbstractResourceReporter):
    def __init__(self, config: PermitConfig, registry: ResourceRegistry):
        self._config = config
        self._registry = registry
        self._logger = logger.bind(name="permit.resources.reporter")
        self._headers = {
            "Authorization": f"Bearer {self._config.token}",
            "Content-Type": "application/json",
        }
        self._base_url = self._config.pdp
        self._initialized = True  # TODO: remove this

    async def __aenter__(self):
        await self._sync_resources_to_control_plane()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """
        Context handler to terminate internal tasks
        """
        pass

    @property
    def token(self) -> str:
        return self._config.token

    async def add_resource(self, resource: ResourceDefinition) -> ResourceStub:
        self._registry.add_resource(resource)
        await self._maybe_sync_resource(resource)
        return ResourceStub(self, resource.name)

    async def add_action_to_resource(
        self, resource_name: str, action_def: ActionDefinition
    ):
        action = self._registry.add_action_to_resource(resource_name, action_def)
        if action is not None:
            await self._maybe_sync_action(action)

    async def _maybe_sync_resource(self, resource: ResourceDefinition):
        if self._initialized and not self._registry.is_synced(resource):
            self._logger.info(f"syncing resource: {repr(resource)}")
            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.put(
                        f"{self._base_url}/cloud/resources/{resource.name}",
                        data=json.dumps(resource.dict()),
                    ) as response:
                        content: dict = await response.json()
                        remote_id: str = content.get("id", None)
                        if remote_id is not None:
                            self._registry.mark_as_synced(resource, remote_id=remote_id)
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to sync resource {resource.name}, got error: {err}"
                    )

    async def _maybe_sync_action(self, action: ActionDefinition):
        resource_id = action.resource_id
        if resource_id is None:
            return

        if self._initialized and not self._registry.is_synced(action):
            self._logger.info(f"syncing action: {repr(action)}")
            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.put(
                        f"{self._base_url}/cloud/resources/{resource_id}/actions",
                        data=json.dumps(action.dict()),
                    ) as response:
                        content: dict = await response.json()
                        remote_id: str = content.get("id", None)
                        if remote_id is not None:
                            self._registry.mark_as_synced(action, remote_id=remote_id)
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to sync action {action.name}, got error: {err}"
                    )

    async def _sync_resources_to_control_plane(self):
        for resource in self._registry.resources:
            await self._maybe_sync_resource(resource)

    async def resource(self, config: ResourceConfig) -> ResourceStub:
        resource = ResourceDefinition(
            name=config.name,
            type=config.type,
            path=config.path,
            description=config.description,
            actions=config.actions or [],
            attributes=config.attributes or {},
        )
        return await self.add_resource(resource)

    def action(self, config: ActionConfig) -> ActionDefinition:
        return ActionDefinition(
            name=config.name,
            title=config.title,
            description=config.description,
            path=config.path,
            attributes=config.attributes or {},
        )

    async def sync_resources(self, config: ResourceTypes) -> List[ResourceStub]:
        stubs: List[ResourceStub] = []

        for resource in config.resources:
            actions = []
            for actionName, action in iter(resource.actions.items()):
                actions.append(
                    ActionDefinition(
                        name=actionName,
                        title=action.title or actionName,
                        description=action.description,
                        path=action.path,
                        attributes=action.attributes or {},
                    )
                )

            stub = await self.add_resource(
                ResourceDefinition(
                    name=resource.type,
                    type="rest",
                    path=f"/resources/{resource.type}",
                    description=resource.description,
                    actions=actions,
                    attributes=resource.attributes or {},
                )
            )
            stubs.append(stub)

        return stubs
