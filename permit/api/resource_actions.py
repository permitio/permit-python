from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.resource_actions import (
    create_resource_action,
    delete_resource_action,
    get_resource_action,
    list_resource_actions,
    update_resource_action,
)
from permit.openapi.models import (
    ResourceActionCreate,
    ResourceActionRead,
    ResourceActionUpdate,
)


class ResourceAction(PermitBaseApi):
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
    ) -> List[ResourceActionRead]:
        """
        Lists the resource-actions of a specific resource (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceActionRead
            permit = Permit(...)
            resource_actions: List[ResourceActionRead] = await permit.api.resource_actions.list("document")
            ```
        """
        resource_actions = await list_resource_actions.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(resource_actions, "list", "resource_actions")
        return resource_actions

    @lazy_load_context
    async def get(
        self, resource_key: str, resource_action_key: str
    ) -> ResourceActionRead:
        """
        Gets a resource-action for a given resource key and a resource-action key (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceActionRead
            permit = Permit(...)
            resource_action: ResourceActionRead = await permit.api.resource_actions.get("document", "read")
            ```
        """
        resource_action = await get_resource_action.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            resource_action_key,
            client=self._client,
        )
        raise_for_error_by_action(
            resource_action, "resource_action", resource_action_key
        )
        return resource_action

    @lazy_load_context
    async def get_by_key(
        self, resource_key: str, resource_action_key: str
    ) -> ResourceActionRead:
        """
        Gets a resource-action for a given resource key and a resource-action key (from your context's environment) -
        same as `get()` function.

        Usage Example:
            ```
            from permit import Permit, ResourceActionRead
            permit = Permit(...)
            resource_action: ResourceActionRead = await permit.api.resource_actions.get_by_key("document", "read")
            ```
        """

        return await self.get(resource_key, resource_action_key)

    @lazy_load_context
    async def get_by_id(
        self, resoure_id: UUID, resource_action_id: UUID
    ) -> ResourceActionRead:
        """
        Gets a resource-action for a given resource id and a resource-action id (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, ResourceActionRead
            permit = Permit(...)
            resource_action: ResourceActionRead = await permit.api.resource_actions.get_by_id(UUID("bb88960b-bd68-4908-9900-41acf1096021"), UUID("a0e05e9e-2b36-49d0-8d90-f603f90b62a7"))
            ```
        """
        return await self.get(resoure_id.hex, resource_action_id.hex)

    @lazy_load_context
    async def create(
        self, resource_key: str, resource_action: Union[ResourceActionCreate, dict]
    ) -> ResourceActionRead:
        """
        Creates a resource-action for a specific resource (by key) - can be either ResourceActionCreate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, ResourceActionRead, ResourceActionCreate
            permit = Permit(...)
            resource_action_create = ResourceActionCreate(
                key="read",
                name="Read",
                description="Read a document action"
            )
            resource_action: ResourceActionRead = await permit.api.resource_actions.create("document", resource_action_create)
            ```
        """
        if isinstance(resource_action, dict):
            json_body = ResourceActionCreate.parse_obj(resource_action)
        else:
            json_body = resource_action
        resource_action = await create_resource_action.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource_action, "resource_action", json.dumps(json_body.dict()), "create"
        )
        return resource_action

    @lazy_load_context
    async def update(
        self,
        resource_key: str,
        resource_action_key: str,
        resource_action: Union[ResourceActionUpdate, dict],
    ) -> ResourceActionRead:
        """
        Creates a resource-action for a specific resource (by key) - given a resource key and a resource-action key -
        can be either ResourceActionUpdate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, ResourceActionRead, ResourceActionUpdate
            permit = Permit(...)
            resource_action_update = ResourceActionUpdate(
                name="Read",
                description="Read a document action"
            )
            resource_action: ResourceActionRead = await permit.api.resource_actions.update("document", "read", resource_action_update)
            ```
        """
        if isinstance(resource_action, dict):
            json_body = ResourceActionUpdate.parse_obj(resource_action)
        else:
            json_body = resource_action
        updated_resource_action = await update_resource_action.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            resource_action_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            resource_action, "resource_action", json.dumps(json_body.dict()), "update"
        )
        return updated_resource_action

    @lazy_load_context
    async def delete(self, resource_key: str, resource_action_key: str):
        """
        Deletes a resource-action for a specific resource (by key) - given a resource key and a resource-action key.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.resource_actions.delete("document", "read")
            ```
        """
        res = await delete_resource_action.asyncio(
            self._config.context.project,
            self._config.context.environment,
            resource_key,
            resource_action_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "resource_action", resource_action_key, "delete")
