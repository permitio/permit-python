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
        """
        Lists the roles from your context's environment.

        Usage Example:
            ```
            from permit import Permit, RoleRead
            permit = Permit(...)
            roles: List[RoleRead] = await permit.api.roles.list()
            ```
        """
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
        """
        Gets a role for a given role key (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, RoleRead
            permit = Permit(...)
            role: RoleRead = await permit.api.roles.get("viewer")
            ```
        """
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
        """
        Gets a role for a given role key (from your context's environment) - same as `get()` function.

        Usage Example:
            ```
            from permit import Permit, RoleRead
            permit = Permit(...)
            role: RoleRead = await permit.api.roles.get_by_key("viewer")
            ```
        """
        return await self.get(role_key)

    @lazy_load_context
    async def get_by_id(self, role_id: UUID) -> RoleRead:
        """
        Gets a role for a given role id (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, RoleRead
            permit = Permit(...)
            role: RoleRead = await permit.api.roles.get_by_id(UUID("19699803-292b-4fcb-b492-30740165d3cc"))
            ```
        """
        return await self.get(role_id.hex)

    @lazy_load_context
    async def create(self, role: Union[RoleCreate, dict]) -> RoleRead:
        """
        Creates a role under the context's environment - can be either RoleCreate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, RoleRead, RoleCreate
            permit = Permit(...)
            role_create = RoleCreate(
                key="reader",
                name="Reader",
                description="A Reader role within our application",
                permissions=["document:read"]
                )
            role: RoleRead = await permit.api.roles.create(role_create)
            ```
        """
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
        """
        Updates a role under the context's environment - by a given role key -
        can be either RoleUpdate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, RoleRead, RoleUpdate
            permit = Permit(...)
            role_update = RoleUpdate(
                name="Reader",
                description="A Reader role within our application",
                permissions=["document:read"]
                )
            role: RoleRead = await permit.api.roles.update("reader", role_update)
            ```
        """
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
        """
        Deletes a role under the context's environment - by a given role key.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.roles.delete("reader")
            ```
        """
        res = await delete_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "role", role_key, "delete")

    # Permissions assignment methods
    @lazy_load_context
    async def assign_permissions(self, role_key: str, permissions: List[str]) -> RoleRead:
        """
        Assign a list of permissions to a role under the context's environment -
        by a given role key and list of permissions.
        If a permission is already granted to the role it is skipped.
        Each permission can be either a resource-action id, or {resource_key}:{action_key}, i.e: the "document:read".

        Usage Example:
            ```
            from permit import Permit, RoleRead
            permit = Permit(...)
            role: RoleRead = await permit.api.roles.assign_permissions("reader", ["document:read", "document:delete"])
            ```
        """
        json_body = AddRolePermissions.parse_obj(permissions)
        res = await assign_permissions_to_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(res, "role", f"permissions: {permissions}", "update")
        return res

    @lazy_load_context
    async def remove_permissions(self, role_key: str, permissions: List[str]):
        """
        Removes a list of permissions from a role under the context's environment -
        by a given role key and list of permissions.
        If a permission is not found it is skipped.
        Each permission can be either a resource-action id, or {resource_key}:{action_key}, i.e: the "document:read".

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.roles.remove_permissions("reader", ["document:read", "document:delete"])
            ```
        """
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
    async def add_parent_role(self, role_key: str, parent_role_key: str) -> RoleRead:
        """
        Add a parent role to a role under the context's environment -
        by a given role key and a parent-role key.
        Makes a role extend the parent role.
        In other words, a role will automatically be assigned any permissions that are granted to the parent role.
        We can say the role extends the parent role or inherits from the parent role.

        Usage Example:
            ```
            from permit import Permit, RoleRead
            permit = Permit(...)
            role: RoleRead = await permit.api.roles.add_parent_role("child-role", "parent-role")
            ```
        """
        role = await add_parent_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            role_key,
            parent_role_key,
            client=self._client,
        )
        raise_for_error_by_action(
            role, "role", f"parent-role: {parent_role_key}", "update"
        )
        return role

    @lazy_load_context
    async def remove_parent_role(self, role_key: str, parent_role_key: str):
        """
        Removes a parent role from a role under the context's environment -
        by a given role key and a parent-role key.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.roles.remove_parent_role("child-role", "parent-role")
            ```
        """

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
