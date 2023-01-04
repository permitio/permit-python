from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_scope
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
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


class ResourceAttribute(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,
        scope: Optional[APIKeyScopeRead],
        logger: Logger,
    ):
        super().__init__(client=client, config=config, scope=scope, logger=logger)

    # CRUD Methods
    @lazy_load_scope
    async def list(
        self, resource_key: str, page: int = 1, per_page: int = 100
    ) -> List[ResourceAttributeRead]:
        resource_attributes = await list_resource_attributes.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(resource_attributes, "list", "resource_attributes")
        return resource_attributes

    @lazy_load_scope
    async def get(
        self, resource_key: str, resource_attribute_key: str
    ) -> ResourceAttributeRead:
        resource_attribute = await get_resource_attribute.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            resource_attribute_key,
            client=self._client,
        )
        raise_for_error_by_action(
            resource_attribute, "resource_attribute", resource_attribute_key
        )
        return resource_attribute

    @lazy_load_scope
    async def get_by_key(
        self, resource_key: str, resource_attribute_key: str
    ) -> ResourceAttributeRead:
        return await self.get(resource_key, resource_attribute_key)

    @lazy_load_scope
    async def get_by_id(
        self, resource_id: UUID, resource_attribute_id: UUID
    ) -> ResourceAttributeRead:
        return await self.get(resource_id.hex, resource_attribute_id.hex)

    @lazy_load_scope
    async def create(
        self,
        resource_key: str,
        resource_attribute: Union[ResourceAttributeCreate, dict],
    ) -> ResourceAttributeRead:
        if isinstance(resource_attribute, dict):
            json_body = ResourceAttributeCreate.parse_obj(resource_attribute)
        else:
            json_body = resource_attribute
        resource_attribute = await create_resource_attribute.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
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

    @lazy_load_scope
    async def update(
        self,
        resource_key: str,
        resource_attribute_key: str,
        resource_attribute: Union[ResourceAttributeUpdate, dict],
    ) -> ResourceAttributeRead:
        if isinstance(resource_attribute, dict):
            json_body = ResourceAttributeUpdate.parse_obj(resource_attribute)
        else:
            json_body = resource_attribute
        updated_resource_attribute = await update_resource_attribute.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
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

    @lazy_load_scope
    async def delete(self, resource_key: str, resource_attribute_key: str):
        res = await delete_resource_attribute.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            resource_attribute_key,
            client=self._client,
        )
        raise_for_error_by_action(
            res, "resource_attribute", resource_attribute_key, "delete"
        )
