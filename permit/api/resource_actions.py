from __future__ import annotations

import json
from typing import Optional, List, Union
from uuid import UUID

from permit import PermitConfig
from permit.api.client import PermitBaseApi, lazy_load_scope
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.resource_actions import list_resource_actions, get_resource_action, create_resource_action, \
    update_resource_action, delete_resource_action
from permit.openapi.models import ResourceActionRead, ResourceActionCreate, ResourceActionUpdate
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


class ResourceAction(PermitBaseApi):
    def __init__(self, client, config: PermitConfig, scope: Optional[APIKeyScopeRead]):
        super().__init__(client=client, config=config, scope=scope)

    # CRUD Methods
    @lazy_load_scope
    async def list(self, resource_key: str, page: int = 1, per_page: int = 100) -> List[ResourceActionRead]:
        resource_actions = await list_resource_actions.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(resource_actions, "list", "resource_actions")
        return resource_actions

    @lazy_load_scope
    async def get(self, resource_key: str, resource_action_key: str) -> ResourceActionRead:
        resource_action = await get_resource_action.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            resource_action_key,
            client=self._client,
        )
        raise_for_error_by_action(resource_action, "resource_action", resource_action_key)
        return resource_action

    @lazy_load_scope
    async def get_by_key(self, resource_key: str, resource_action_key: str) -> ResourceActionRead:
        return await self.get(resource_key, resource_action_key)

    @lazy_load_scope
    async def get_by_id(self, resoure_id: UUID, resource_action_id: UUID) -> ResourceActionRead:
        return await self.get(resoure_id.hex, resource_action_id.hex)

    @lazy_load_scope
    async def create(self, resource_key: str, resource_action: Union[ResourceActionCreate, dict]) -> ResourceActionRead:
        if isinstance(resource_action, dict):
            json_body = ResourceActionCreate.parse_obj(resource_action)
        else:
            json_body = resource_action
        resource_action = await create_resource_action.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(resource_action, "resource_action", json.dumps(json_body.dict()), "create")
        return resource_action

    @lazy_load_scope
    async def update(
        self, resource_key: str, resource_action_key: str, resource_action: Union[ResourceActionUpdate, dict]
    ) -> ResourceActionRead:
        if isinstance(resource_action, dict):
            json_body = ResourceActionUpdate.parse_obj(resource_action)
        else:
            json_body = resource_action
        updated_resource_action = await update_resource_action.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            resource_action_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(resource_action, "resource_action", json.dumps(json_body.dict()), "update")
        return updated_resource_action

    @lazy_load_scope
    async def delete(self, resource_key: str, resource_action_key: str):
        res = await delete_resource_action.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            resource_key,
            resource_action_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "resource_action", resource_action_key, "delete")