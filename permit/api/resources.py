from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.api.resource_actions import ResourceAction
from permit.api.resource_attributes import ResourceAttribute
from permit.config import PermitConfig
from permit.exceptions.exceptions import PermitNotFound, raise_for_error_by_action
from permit.openapi.api.resources import (
    create_resource,
    delete_resource,
    get_resource,
    list_resources,
    update_resource,
)
from permit.openapi.models import (
    ActionBlockEditable,
    AttributeBlock,
    ResourceActionRead,
    ResourceAttributeRead,
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
)


class Resource(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,
        logger: Logger,
        resource_attributes: ResourceAttribute,
        resource_actions: ResourceAction,
    ):
        super().__init__(client=client, config=config, logger=logger)
        self.resource_attributes = resource_attributes
        self.resource_actions = resource_actions

    # CRUD Methods
    @lazy_load_context
    async def list(self, page: int = 1, per_page: int = 100) -> List[ResourceRead]:
        """
        Lists the resources from your context's environment.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resources: List[ResourceRead] = await permit.api.resources.list()
            ```
        """
        resources = await list_resources.asyncio(
            self._config.context.project,
            self._config.context.environment,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(resources, "list", "resources")
        return resources

    @lazy_load_context
    async def get(self, resource_key: str) -> ResourceRead:
        """
        Gets a resource for a given resource key (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.get("document")
            ```
        """
        resource = await get_resource.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            client=self._client,
        )
        raise_for_error_by_action(resource, "resource", resource_key)
        return resource

    @lazy_load_context
    async def get_by_key(self, resource_key: str) -> ResourceRead:
        """
        Gets a resource for a given resource key (from your context's environment) - same as `get()` function.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.get_by_key("document")
            ```
        """
        return await self.get(resource_key)

    @lazy_load_context
    async def get_by_id(self, resource_id: UUID) -> ResourceRead:
        """
        Gets a resource for a given resource id (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.get_by_id(UUID("984658dd-06bc-4e1e-840b-6a8092c1d481"))
            ```
        """
        return await self.get(resource_id.hex)

    @lazy_load_context
    async def create(self, resource: Union[ResourceCreate, dict]) -> ResourceRead:
        """
        Creates a resource under the context's environment - can be either ResourceCreate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, ResourceRead, ResourceCreate
            permit = Permit(...)
            resource_create = ResourceCreate(
                key="document",
                name="Document",
                description="A document resource within our application",
                )
            resource: ResourceRead = await permit.api.resources.create(resource_create)
            ```
        """
        if isinstance(resource, dict):
            json_body = ResourceCreate.parse_obj(resource)
        else:
            json_body = resource
        created_resource = await create_resource.asyncio(
            self._config.context.project,
            self._config.context.environment,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource, "resource", json.dumps(json_body.dict()), "create"
        )
        return created_resource

    @lazy_load_context
    async def update(
        self, resource_key: str, resource: Union[ResourceUpdate, dict]
    ) -> ResourceRead:
        """
        Updates a resource under the context's environment - by a given resource key -
        can be either ResourceUpdate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, ResourceRead, ResourceUpdate
            permit = Permit(...)
            resource_update = ResourceUpdate(
                name="Document",
                description="A document resource within our application",
                )
            resource: ResourceRead = await permit.api.resources.update("document", resource_update)
            ```
        """
        if isinstance(resource, dict):
            json_body = ResourceUpdate.parse_obj(resource)
        else:
            json_body = resource
        updated_resource = await update_resource.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource, "resource", json.dumps(json_body.dict()), "update"
        )
        return updated_resource

    @lazy_load_context
    async def delete(self, resource_key: str | ResourceRead) -> None:
        """
        Deletes a resource under the context's environment - by a given resource key.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.resources.delete("document")
            ```
        """
        res = await delete_resource.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "resource", resource_key, "delete")

    # Resource Attributes Methods
    async def add_resource_attribute(
        self, resource_key: str, resource_attribute_key: str
    ) -> ResourceRead:
        """
        Add a resource-attribute to a resource under the context's environment -
        by a given resource key and a resource-attribute key.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.add_resource_attribute("document", "pages")
            ```
        """
        exist_resource_attributes: dict = (await self.get(resource_key)).attributes
        resource_attribute_to_add: ResourceAttributeRead = (
            await self.resource_attributes.get(resource_attribute_key)
        )
        attribute_block = AttributeBlock(
            type=resource_attribute_to_add.type,
            description=resource_attribute_to_add.description,
        )
        exist_resource_attributes[resource_attribute_to_add.key] = attribute_block
        resource_update = ResourceUpdate(attributes=exist_resource_attributes)
        return await self.update(resource_key, resource_update)

    async def remove_resource_attribute(
        self, resource_key: str, resource_attribute_key: str
    ) -> ResourceRead:
        """
        Removes a resource-attribute from a resource under the context's environment -
        by a given resource key and a resource-attribute key.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.remove_resource_attribute("document", "pages")
            ```
        """

        exist_resource_attributes: dict = (await self.get(resource_key)).attributes
        attribute_to_remove = exist_resource_attributes.pop(
            resource_attribute_key, None
        )
        if attribute_to_remove is None:
            raise PermitNotFound("resource_attribute", resource_attribute_key)
        resource_update = ResourceUpdate(attributes=exist_resource_attributes)
        return await self.update(resource_key, resource_update)

    async def set_resource_attributes(
        self, resource_key: str, resource_attribute_keys: List[str]
    ) -> ResourceRead:
        """
        Set a resource-attributes list to a resource under the context's environment -
        by a given resource key and a list of resource-attributes keys.
        All resource-attributes that were for the resource will be overridden.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.set_resource_attributes("document", ["pages", "author"])
            ```
        """

        attribute_block_list: List[AttributeBlock] = []
        for resource_attribute_key in resource_attribute_keys:
            resource_attribute: ResourceAttributeRead = (
                await self.resource_attributes.get(resource_attribute_key)
            )
            attribute_block_list.append(
                AttributeBlock(
                    type=resource_attribute.type,
                    description=resource_attribute.description,
                )
            )
        resource_update = ResourceUpdate(attributes=attribute_block_list)
        return await self.update(resource_key, resource_update)

    # Resource Actions Methods
    async def add_resource_action(
        self, resource_key: str, resource_action_key: str
    ) -> ResourceRead:
        """
        Add a resource-action to a resource under the context's environment -
        by a given resource key and a resource-action key.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.add_resource_action("document", "read")
            ```
        """
        exist_resource_actions: dict = (await self.get(resource_key)).actions
        resource_action_to_add: ResourceActionRead = await self.resource_actions.get(
            resource_action_key
        )
        action_block = ActionBlockEditable(
            name=resource_action_to_add.name,
            description=resource_action_to_add.description,
        )
        exist_resource_actions[resource_action_to_add.key] = action_block
        resource_update = ResourceUpdate(actions=exist_resource_actions)
        return await self.update(resource_key, resource_update)

    async def remove_resource_action(
        self, resource_key: str, resource_action_key: str
    ) -> ResourceRead:
        """
        Removes a resource-action from a resource under the context's environment -
        by a given resource key and a resource-action key.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.remove_resource_action("document", "read")
            ```
        """
        exist_resource_actions: dict = (await self.get(resource_key)).actions
        action_to_remove = exist_resource_actions.pop(resource_action_key, None)
        if action_to_remove is None:
            raise PermitNotFound("resource_action", resource_action_key)
        resource_update = ResourceUpdate(actions=exist_resource_actions)
        return await self.update(resource_key, resource_update)

    async def set_resource_actions(
        self, resource_key: str, resource_action_keys: List[str]
    ) -> ResourceRead:
        """
        Set a resource-actions list to a resource under the context's environment -
        by a given resource key and a list of resource-action keys.
        All resource-actions that were for the resource will be overridden.

        Usage Example:
            ```
            from permit import Permit, ResourceRead
            permit = Permit(...)
            resource: ResourceRead = await permit.api.resources.set_resource_action("document", ["read", "delete", "edit"])
            ```
        """

        action_block_list: List[ActionBlockEditable] = []
        for resource_action_key in resource_action_keys:
            resource_action: ResourceActionRead = await self.resource_actions.get(
                resource_action_key
            )
            action_block_list.append(
                ActionBlockEditable(
                    name=resource_action.name, description=resource_action.description
                )
            )
        resource_update = ResourceUpdate(actions=action_block_list)
        return await self.update(resource_key, resource_update)
