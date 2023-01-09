from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.resource_attributes import (
    create_resource_attribute,
    delete_resource_attribute,
    get_resource_attribute,
    list_resource_attributes,
    update_resource_attribute,
)
from permit.openapi.models import (
    ResourceAttributeCreate,
    ResourceAttributeRead,
    ResourceAttributeUpdate,
)


class ResourceAttribute(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,
        logger: Logger,
    ):
        super().__init__(client=client, config=config, logger=logger)

    # CRUD Methods
    @lazy_load_context
    async def list(
        self, resource_key: str, page: int = 1, per_page: int = 100
    ) -> List[ResourceAttributeRead]:
        """
        Lists the resource-attributes of a specific resource (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceActionRead
            permit = Permit(...)
            resource_attributes: List[ResourceActionRead] = await permit.api.resource_attributes.list("document")
            ```
        """
        resource_attributes = await list_resource_attributes.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(resource_attributes, "list", "resource_attributes")
        return resource_attributes

    @lazy_load_context
    async def get(
        self, resource_key: str, resource_attribute_key: str
    ) -> ResourceAttributeRead:
        """
        Gets a resource-attribute for a given resource key and a resource-attribute key
        (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceAttributeRead
            permit = Permit(...)
            resource_attribute: ResourceAttributeRead = await permit.api.resource_attributes.get("document", "pages")
            ```
        """
        resource_attribute = await get_resource_attribute.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            resource_attribute_key,
            client=self._client,
        )
        raise_for_error_by_action(
            resource_attribute, "resource_attribute", resource_attribute_key
        )
        return resource_attribute

    @lazy_load_context
    async def get_by_key(
        self, resource_key: str, resource_attribute_key: str
    ) -> ResourceAttributeRead:
        """
        Gets a resource-attribute for a given resource key and a resource-attribute key - same as `get()` function.
        (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceAttributeRead
            permit = Permit(...)
            resource_attribute: ResourceAttributeRead = await permit.api.resource_attributes.get_by_key("document", "pages")
            ```
        """
        return await self.get(resource_key, resource_attribute_key)

    @lazy_load_context
    async def get_by_id(
        self, resource_id: UUID, resource_attribute_id: UUID
    ) -> ResourceAttributeRead:
        """
        Gets a resource-attribute for a given resource id and a resource-attribute id (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceAttributeRead
            permit = Permit(...)
            resource_attribute: ResourceAttributeRead = await permit.api.resource_attributes.get_by_id(UUID("5b41f499-fb9b-478b-9b10-8df4616a56e7"), UUID("44d336e2-93eb-4523-8196-5f734eef2cb4"))
            ```
        """
        return await self.get(resource_id.hex, resource_attribute_id.hex)

    @lazy_load_context
    async def create(
        self,
        resource_key: str,
        resource_attribute: Union[ResourceAttributeCreate, dict],
    ) -> ResourceAttributeRead:
        """
        Creates a resource-attribute for a specific resource (by key) - can be either ResourceAttributeCreate or a
        dictionary.

        Usage Example:
            ```
            from permit import Permit, ResourceAttributeRead, ResourceAttributeCreate
            permit = Permit(...)
            resource_attribute_create = ResourceActionCreate(
                key="pages",
                name="Pages",
                description="Pages count for a document attribute"
            )
            resource_attribute: ResourceAttributeRead = await permit.api.resource_attributes.create("document", resource_attribute_create)
            ```
        """

        if isinstance(resource_attribute, dict):
            json_body = ResourceAttributeCreate.parse_obj(resource_attribute)
        else:
            json_body = resource_attribute
        resource_attribute = await create_resource_attribute.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource_attribute,
            "resource_attribute",
            json.dumps(json_body.dict()),
            "create",
        )
        return resource_attribute

    @lazy_load_context
    async def update(
        self,
        resource_key: str,
        resource_attribute_key: str,
        resource_attribute: Union[ResourceAttributeUpdate, dict],
    ) -> ResourceAttributeRead:
        """
        Creates a resource-attribute for a specific resource (by key) - given a resource key and a resource-attribute key -
        can be either ResourceAttributeUpdate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, ResourceAttributeRead, ResourceAttributeUpdate
            permit = Permit(...)
            resource_attribute_update = ResourceAttributeUpdate(
                name="Pages",
                description="Pages count for a document attribute"
            )
            resource_attribute: ResourceAttributeRead = await permit.api.resource_attributes.update("document", "pages", resource_attribute_update)
            ```
        """
        if isinstance(resource_attribute, dict):
            json_body = ResourceAttributeUpdate.parse_obj(resource_attribute)
        else:
            json_body = resource_attribute
        updated_resource_attribute = await update_resource_attribute.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            resource_attribute_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource_attribute,
            "resource_attribute",
            json.dumps(json_body.dict()),
            "update",
        )
        return updated_resource_attribute

    @lazy_load_context
    async def delete(self, resource_key: str, resource_attribute_key: str):
        """
        Deletes a resource-attribute for a specific resource (by key) -
        given a resource key and a resource-attribute key.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.resource_attributes.delete("document", "pages")
            ```
        """
        res = await delete_resource_attribute.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            resource_attribute_key,
            client=self._client,
        )
        raise_for_error_by_action(
            res, "resource_attribute", resource_attribute_key, "delete"
        )
