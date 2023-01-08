from __future__ import annotations

import asyncio
import json
from enum import Enum
from typing import Awaitable, Callable, Dict, Generic, List, Optional, TypeVar, Union

from loguru import logger
from pydantic import BaseModel
from typing_extensions import ParamSpec

from permit.api.base import lazy_load_context
from permit.api.elements import Elements
from permit.api.environments import Environment
from permit.api.projects import Project
from permit.api.resource_actions import ResourceAction
from permit.api.resource_attributes import ResourceAttribute
from permit.api.resources import Resource
from permit.api.roles import Role
from permit.api.tenants import Tenant
from permit.api.users import User
from permit.config import PermitConfig, PermitContext
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi import AuthenticatedClient
from permit.openapi.api.users import create_user, get_user, update_user
from permit.openapi.models import UserCreate, UserRead, UserUpdate
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead
from permit.resources.interfaces import OnUserCreation

T = TypeVar("T")

AsyncCallback = Callable[[], Awaitable[Dict]]


class Operation(Generic[T]):
    def __init__(self, callback: AsyncCallback):
        self._callback = callback

    async def run(self) -> T:
        return await self._callback()


class ReadOperation(Operation[Dict]):
    pass


class WriteOperation(Operation[Dict]):
    pass


class PermitApiClient:
    def __init__(self, config: PermitConfig):
        self._config = config
        self._logger = logger.bind(name="permit.mutations.client")
        self.client = AuthenticatedClient(base_url=config.api_url, token=config.token)
        self.scope: Optional[APIKeyScopeRead] = None
        self.tenants: Tenant = Tenant(
            self.client, self._config, self.scope, self._logger
        )
        self.environments: Environment = Environment(
            self.client, self._config, self.scope, self._logger
        )
        self.projects: Project = Project(
            self.client, self._config, self.scope, self._logger
        )
        self.resource_actions: ResourceAction = ResourceAction(
            self.client, self._config, self.scope, self._logger
        )
        self.resource_attributes: ResourceAttribute = ResourceAttribute(
            self.client, self._config, self.scope, self._logger
        )
        self.resources: Resource = Resource(
            self.client,
            self._config,
            self.scope,
            self._logger,
            self.resource_attributes,
            self.resource_actions,
        )
        self.roles: Role = Role(self.client, self._config, self.scope, self._logger)
        self.users: User = User(self.client, self._config, self.scope, self._logger)
        self.elements: Elements = Elements(
            self.client, self._config, self.scope, self._logger
        )

    # region write api ---------------------------------------------------------------
    async def set_context(self, context: PermitContext):
        if context.project is not None:
            project = await self.projects.get()


    @lazy_load_context
    async def sync_user(self, user: Union[UserCreate, dict], on_create: OnUserCreation) -> UserRead:
        if isinstance(user, dict):
            key = user.get("key", None)
            if key is None:
                raise KeyError("required 'key' in input dictionary")
        else:
            key = user.key
        # check if the user key already exists
        self._logger.info(f"checking if user '{key}' already exists")
        try:
            user_to_update = await self.users.get(key)
        except:
            user_to_update = None

        if user_to_update is not None:
            self._logger.info("user exists, updating it...")
            # if the user exists update it
            if isinstance(user, dict):
                user_update = UserUpdate.parse_obj(user)
            else:
                user_update = UserUpdate.parse_obj(user.dict(exclude={"key"}))
            updated_user = await self.users.update(
                key,
                user_update
            )
            return updated_user
        # otherwise create the user
        self._logger.info("user does not exist, creating it...")
        created_user = await self.users.create(user)

        # Set initial roles when new user is created
        for initial_role in on_create.initial_roles:
            await self.api.users.assign_role(key, initial_role.role, initial_role.tenant)

        return created_user

    # endregion
    # region cloud api proxy ---------------------------------------------------------
    @staticmethod
    async def read(*operations: ReadOperation) -> List[Dict]:
        # reads do not need to be resolved in order, can be in parallel
        return list(await asyncio.gather(*(op.run() for op in operations)))

    @staticmethod
    async def write(*operations: WriteOperation) -> List[Dict]:
        # writes must be in order
        results = []
        for op in operations:
            result = await op.run()
            results.append(result)
        return results

    # endregion
