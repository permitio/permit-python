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
        """
        Lists the users from your context's environment.

        Usage Example:
            ```
            from permit import Permit, UserRead
            permit = Permit(...)
            users: List[UserRead] = await permit.api.users.list()
            ```
        """
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
        """
        Gets a user for a given user key (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, UserRead
            permit = Permit(...)
            user: UserRead = await permit.api.users.get("joe")
            ```
        """
        user = await get_user.asyncio(
            self._config.context.project,
            self._config.context.environment,
            user_key,
            client=self._client,
        )
        raise_for_error_by_action(user, "user", user_key)
        return user

    @lazy_load_context
    async def get_by_key(self, user_key: str) -> UserRead:
        """
        Gets a user for a given user key (from your context's environment) - same as `get()` function.

        Usage Example:
            ```
            from permit import Permit, UserRead
            permit = Permit(...)
            user: UserRead = await permit.api.users.get_by_key("joe")
            ```
        """
        return await self.get(user_key)

    @lazy_load_context
    async def get_by_id(self, user_id: UUID) -> UserRead:
        """
        Gets a user for a given user id (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, UserRead
            permit = Permit(...)
            user: UserRead = await permit.api.users.get_by_id(UUID("6d785f2a-0b0d-4469-b994-b2f3bdb3a948"))
            ```
        """
        return await self.get(user_id.hex)

    @lazy_load_context
    async def create(self, user: Union[UserCreate, dict]) -> UserRead:
        """
        Creates a user under the context's environment - can be either UserCreate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, UserRead, UserCreate
            permit = Permit(...)
            user_create = UserCreate(
                key="auth0_6ddc1215-e6e0-4888-bf23-41d58b09f678",
                email="john@doe.com",
                first_name="John",
                last_name="Doe",
                )
            user: UserRead = await permit.api.users.create(user_create)
            ```
        """
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
        """
        Updates a user under the context's environment - by a given user key - can be either UserUpdate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, UserRead, UserUpdate
            permit = Permit(...)
            user_update = UserUpdate(
                email="john@doe.com",
                first_name="Johnny",
                last_name="Doe"
                )
            user: UserRead = await permit.api.users.update("auth0_6ddc1215-e6e0-4888-bf23-41d58b09f678", user_update)
            ```
        """
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
        """
        Deletes a user under the context's environment - by a given user key.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.users.delete("auth0_6ddc1215-e6e0-4888-bf23-41d58b09f678")
            ```
        """
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
        """
        Assign a role to a user under the context's environment - by a given user key, role key and tenant key.
        If no tenant key is given, your context's tenant will be used instead.

        Usage Example:
            ```
            from permit import Permit, RoleAssignmentRead
            permit = Permit(...)
            role_assignment: RoleAssignmentRead = await permit.api.users.assign_role(
                                                     "auth0_6ddc1215-e6e0-4888-bf23-41d58b09f678",
                                                     "reader",
                                                     "rnd"
                                                    )
            ```
        """
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
        """
        Unassign (removes) a role from a user under the context's environment -
        by a given user key, role key and tenant key.
        If no tenant key is given, your context's tenant will be used instead.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.users.unassign_role(
                                             "auth0_6ddc1215-e6e0-4888-bf23-41d58b09f678",
                                             "reader",
                                             "rnd"
                                            )
            ```
        """

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
        tenant_key: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        """
        List all roles assigned to a user under the context's environment -
        by a given user key, role key and tenant key.
        If no tenant key is given, your context's tenant will be used instead.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.users.get_assigned_roles(
                                             "auth0_6ddc1215-e6e0-4888-bf23-41d58b09f678",
                                             "rnd"
                                            )
            ```
        """

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
