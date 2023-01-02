from __future__ import annotations

import json
from typing import Optional, List, Union
from uuid import UUID

from permit import PermitConfig
from permit.api.client import PermitBaseApi, lazy_load_scope
from permit.api.resource_actions import ResourceAction
from permit.api.resource_attributes import ResourceAttribute
from permit.exceptions.exceptions import raise_for_error_by_action, PermitNotFound
from permit.openapi.api.resources import list_resources, get_resource, update_resource, create_resource, \
    delete_resource
from permit.openapi.models import ResourceRead, ResourceUpdate, ResourceCreate, AttributeBlock, ResourceAttributeRead, \
    ResourceActionRead, ActionBlockEditable
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


class Resource(PermitBaseApi):
    def __init__(self, client, config: PermitConfig, scope: Optional[APIKeyScopeRead],
                 resource_attributes: ResourceAttribute, resource_actions: ResourceAction):
        super().__init__(client=client, config=config, scope=scope)
        self.resource_attributes = resource_attributes
        self.resource_actions = resource_actions

    # CRUD Methods
    @lazy_load_scope
    async def list(self, page: int = 1, per_page: int = 100) -> List[ResourceRead]:
        resources = await list_resources.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(resources, "list", "resources")
        return resources

    @lazy_load_scope
    async def get(self, resource_key: str) -> ResourceRead:
        resource = await get_resource.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            client=self._client,
        )
        raise_for_error_by_action(resource, "resource", resource_key)
        return resource

    @lazy_load_scope
    async def get_by_id(self, resource_id: UUID) -> ResourceRead:
        return await self.get(resource_id.hex)

    @lazy_load_scope
    async def get_by_key(self, resource_key: str) -> ResourceRead:
        return await self.get(resource_key)

    @lazy_load_scope
    async def create(self, resource: Union[ResourceCreate, dict]) -> ResourceRead:
        if isinstance(resource, dict):
            json_body = ResourceCreate.parse_obj(resource)
        else:
            json_body = resource
        created_resource = await create_resource.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource, "resource", json.dumps(json_body.dict()), "create"
        )
        return created_resource

    @lazy_load_scope
    async def update(
        self, resource_key: str, resource: Union[ResourceUpdate, dict]
    ) -> ResourceRead:
        if isinstance(resource, dict):
            json_body = ResourceUpdate.parse_obj(resource)
        else:
            json_body = resource
        updated_resource = await update_resource.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource, "resource", json.dumps(json_body.dict()), "update"
        )
        return updated_resource

    @lazy_load_scope
    async def delete(self, resource_key: str | ResourceRead) -> None:
        res = await delete_resource.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "resource", resource_key, "delete")

    # Resource Attributes Methods
    async def add_resource_attribute(self, resource_key: str, resource_attribute_key: str):
        exist_resource_attributes: dict = (await self.get(resource_key)).attributes
        resource_attribute_to_add: ResourceAttributeRead = await self.resource_attributes.get(resource_attribute_key)
        attribute_block = AttributeBlock(type=resource_attribute_to_add.type,
                                         description=resource_attribute_to_add.description)
        exist_resource_attributes[resource_attribute_to_add.key] = attribute_block
        resource_update = ResourceUpdate(attributes=exist_resource_attributes)
        return await self.update(resource_key, resource_update)

    async def remove_resource_attribute(self, resource_key: str, resource_attribute_key: str):
        exist_resource_attributes: dict = (await self.get(resource_key)).attributes
        attribute_to_remove = exist_resource_attributes.pop(resource_attribute_key, None)
        if attribute_to_remove is None:
            raise PermitNotFound("resource_attribute", resource_attribute_key)
        resource_update = ResourceUpdate(attributes=exist_resource_attributes)
        return await self.update(resource_key, resource_update)

    async def set_resource_attributes(self, resource_key: str, resource_attribute_keys: List[str]):
        attribute_block_list: List[AttributeBlock] = []
        for resource_attribute_key in resource_attribute_keys:
            resource_attribute: ResourceAttributeRead = await self.resource_attributes.get(resource_attribute_key)
            attribute_block_list.append(AttributeBlock(type=resource_attribute.type,
                                                       description=resource_attribute.description))
        resource_update = ResourceUpdate(attributes=attribute_block_list)
        return await self.update(resource_key, resource_update)

    # Resource Actions Methods
    async def add_resource_action(self, resource_key: str, resource_action_key: str):
        exist_resource_actions: dict = (await self.get(resource_key)).actions
        resource_action_to_add: ResourceActionRead = await self.resource_actions.get(resource_action_key)
        action_block = ActionBlockEditable(name=resource_action_to_add.name,
                                           description=resource_action_to_add.description)
        exist_resource_actions[resource_action_to_add.key] = action_block
        resource_update = ResourceUpdate(actions=exist_resource_actions)
        return await self.update(resource_key, resource_update)

    async def remove_resource_action(self, resource_key: str, resource_action_key: str):
        exist_resource_actions: dict = (await self.get(resource_key)).actions
        action_to_remove = exist_resource_actions.pop(resource_action_key, None)
        if action_to_remove is None:
            raise PermitNotFound("resource_action", resource_action_key)
        resource_update = ResourceUpdate(actions=exist_resource_actions)
        return await self.update(resource_key, resource_update)

    async def set_resource_actions(self, resource_key: str, resource_action_keys: List[str]):
        action_block_list: List[ActionBlockEditable] = []
        for resource_action_key in resource_action_keys:
            resource_action: ResourceActionRead = await self.resource_actions.get(resource_action_key)
            action_block_list.append(ActionBlockEditable(name=resource_action.name,
                                                         description=resource_action.description))
        resource_update = ResourceUpdate(actions=action_block_list)
        return await self.update(resource_key, resource_update)