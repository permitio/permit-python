from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.role_assignments import (
    assign_role,
    list_role_assignments,
    unassign_role,
)
from permit.openapi.api.users import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)
from permit.openapi.models import (
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
    UserCreate,
    UserRead,
    UserUpdate,
)


class User(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,

        logger: Logger,
    ):
        super().__init__(client=client, config=config, logger=logger)

    # CRUD Methods
    @lazy_load_context
    async def list(self, page: int = 1, per_page: int = 100) -> List[UserRead]:
        users = await list_users.asyncio(
            self._config.context.project,
            self._config.context.environment,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(users, "list", "users")
        return users

    @lazy_load_context
    async def get(self, user_key: str) -> UserRead:
        user = await get_user.asyncio(
            self._config.context.project,
            self._config.context.environment,
            user_key,
            client=self._client,
        )
        raise_for_error_by_action(user, "user", user_key)
        return user

    @lazy_load_context
    async def get_by_id(self, user_id: UUID) -> UserRead:
        return await self.get(user_id.hex)

    @lazy_load_context
    async def get_by_key(self, user_key: str) -> UserRead:
        return await self.get(user_key)

    @lazy_load_context
    async def create(self, user: Union[UserCreate, dict]) -> UserRead:
        if isinstance(user, dict):
            json_body = UserCreate.parse_obj(user)
        else:
            json_body = user
        created_user = await create_user.asyncio(
            self._config.context.project,
            self._config.context.environment,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(user, "user", json.dumps(json_body.dict()), "create")
        return created_user

    @lazy_load_context
    async def update(self, user_key: str, user: Union[UserUpdate, dict]) -> UserRead:
        if isinstance(user, dict):
            json_body = UserUpdate.parse_obj(user)
        else:
            json_body = user
        updated_user = await update_user.asyncio(
            self._config.context.project,
            self._config.context.environment,
            user_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(user, "user", json.dumps(json_body.dict()), "update")
        return updated_user

    @lazy_load_context
    async def delete(self, user_key: str | UserRead) -> None:
        res = await delete_user.asyncio(
            self._config.context.project,
            self._config.context.environment,
            user_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "user", user_key, "delete")

    # Role Assignment Methods
    @lazy_load_context
    async def assign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> RoleAssignmentRead:
        json_body = RoleAssignmentCreate(
            role=role_key, tenant=tenant_key, user=user_key
        )
        role_assignment = await assign_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            role_assignment, "role_assignment", json.dumps(json_body.dict()), "create"
        )
        return role_assignment

    @lazy_load_context
    async def unassign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> None:
        json_body = RoleAssignmentRemove(
            role=role_key, tenant=tenant_key, user=user_key
        )
        unassigned_role = await unassign_role.asyncio(
            self._config.context.project,
            self._config.context.environment,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            unassigned_role,
            "role_assignment",
            f"user:{user_key}, role:{role_key}, tenant:{tenant_key}",
            "delete",
        )

    @lazy_load_context
    async def get_assigned_roles(
        self,
        user_key: str,
        tenant_key: Optional[str],
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        role_assignments = await list_role_assignments.asyncio(
            self._config.context.project,
            self._config.context.environment,
            tenant=tenant_key,
            user=user_key,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(
            role_assignments,
            "role_assignments",
            f"user:{user_key}, tenant:{tenant_key}:",
        )
        return role_assignments
