from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.roles import (
    add_parent_role,
    assign_permissions_to_role,
    create_role,
    delete_role,
    get_role,
    list_roles,
    remove_parent_role,
    remove_permissions_from_role,
    update_role,
)
from permit.openapi.models import (
    AddRolePermissions,
    RemoveRolePermissions,
    RoleAssignmentRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)


class Role(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,

        logger: Logger,
    ):
        super().__init__(client=client, config=config, logger=logger)

    # CRUD Methods
    @lazy_load_context
    async def list(self, page: int = 1, per_page: int = 100) -> List[RoleRead]:
        roles = await list_roles.asyncio(
            self._config.context.project,
            self._config.context.environment,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(roles, "list", "roles")
        return roles

    @lazy_load_context
    async def get(self, role_key: str) -> RoleRead:
        role = await get_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            client=self._client,
        )
        raise_for_error_by_action(role, "role", role_key)
        return role

    @lazy_load_context
    async def get_by_key(self, role_key: str) -> RoleRead:
        return await self.get(role_key)

    @lazy_load_context
    async def get_by_id(self, role_id: UUID) -> RoleRead:
        return await self.get(role_id.hex)

    @lazy_load_context
    async def create(self, role: Union[RoleCreate, dict]) -> RoleRead:
        if isinstance(role, dict):
            json_body = RoleCreate.parse_obj(role)
        else:
            json_body = role
        role = await create_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(role, "role", json.dumps(json_body.dict()), "create")
        return role

    @lazy_load_context
    async def update(self, role_key: str, role: Union[RoleUpdate, dict]) -> RoleRead:
        if isinstance(role, dict):
            json_body = RoleUpdate.parse_obj(role)
        else:
            json_body = role
        updated_role = await update_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(role, "role", json.dumps(json_body.dict()), "update")
        return updated_role

    @lazy_load_context
    async def delete(self, role_key: str):
        res = await delete_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "role", role_key, "delete")

    # Permissions assignment methods
    @lazy_load_context
    async def assign_permissions(self, role_key: str, permissions: List[str]):
        json_body = AddRolePermissions.parse_obj(permissions)
        res = await assign_permissions_to_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(res, "role", f"permissions: {permissions}", "update")

    @lazy_load_context
    async def remove_permissions(self, role_key: str, permissions: List[str]):
        json_body = RemoveRolePermissions.parse_obj(permissions)
        res = await remove_permissions_from_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(res, "role", f"permissions: {permissions}", "remove")

    # Parent Role methods
    @lazy_load_context
    async def add_parent_role(self, role_key: str, parent_role_key: str):
        res = await add_parent_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            parent_role_key,
            client=self._client,
        )
        raise_for_error_by_action(
            res, "role", f"parent-role: {parent_role_key}", "update"
        )

    @lazy_load_context
    async def remove_parent_role(self, role_key: str, parent_role_key: str):
        res = await remove_parent_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            parent_role_key,
            client=self._client,
        )
        raise_for_error_by_action(
            res, "role", f"parent-role: {parent_role_key}", "remove"
        )
