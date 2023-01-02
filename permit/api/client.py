from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Dict, Generic, List, Optional, TypeVar, Union

from loguru import logger
from pydantic import BaseModel
from typing_extensions import ParamSpec

from permit.api.elements import Elements
from permit.api.environments import Environment
from permit.api.projects import Project
from permit.api.resource_actions import ResourceAction
from permit.api.resource_attributes import ResourceAttribute
from permit.api.resources import Resource
from permit.api.roles import Role
from permit.api.tenants import Tenant
from permit.api.users import User
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error, raise_for_error_by_action
from permit.openapi import AuthenticatedClient
from permit.openapi.api.api_keys import get_api_key_scope
from permit.openapi.api.users import create_user, get_user, update_user
from permit.openapi.models import UserCreate, UserRead, UserUpdate
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead

T = TypeVar("T")


class Tenant(BaseModel):
    key: str
    name: str
    description: Optional[str]


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


P = ParamSpec("P")
RT = TypeVar("RT")


def lazy_load_scope(func: Callable[P, RT]) -> Callable[P, Awaitable[RT]]:
    async def wrapper(self: PermitApiClient, *args: P.args, **kwargs: P.kwargs) -> RT:
        if self.scope is None:
            self._logger.info("loading scope propertied from api")
            res = await get_api_key_scope.asyncio(client=self.client)
            raise_for_error(res, message="could not get api key scope")
            self._logger.info("got scope response from api")
            self.scope = res
        else:
            self._logger.debug("scope is already loaded, skipping scope loading")
        return await func(self, *args, **kwargs)

    return wrapper


class PermitBaseApi:
    def __init__(self, client, config: PermitConfig, scope: Optional[APIKeyScopeRead]):
        self._config = config
        self._scope: Optional[APIKeyScopeRead] = scope
        self._client = client


class PermitApiClient:
    def __init__(self, config: PermitConfig):
        self._config = config
        self._logger = logger.bind(name="permit.mutations.client")

        self.client = AuthenticatedClient(base_url=config.api_url, token=config.token)
        self.scope: Optional[APIKeyScopeRead] = None

        self.tenants: Tenant = Tenant(self.client, self._config, self.scope)
        self.environments: Environment = Environment(
            self.client, self._config, self.scope
        )
        self.projects: Project = Project(self.client, self._config, self.scope)
        self.resource_actions: ResourceAction = ResourceAction(
            self.client, self._config, self.scope
        )
        self.resource_attributes: ResourceAttribute = ResourceAttribute(
            self.client, self._config, self.scope
        )
        self.resources: Resource = Resource(
            self.client,
            self._config,
            self.scope,
            self.resource_attributes,
            self.resource_actions,
        )
        self.roles: Role = Role(self.client, self._config, self.scope)
        self.users: User = User(self.client, self._config, self.scope)
        self.elements: Elements = Elements(self.client, self._config, self.scope)

    # region write api ---------------------------------------------------------------

    @lazy_load_scope
    async def sync_user(self, user: Union[UserCreate, dict]) -> UserRead:
        if isinstance(user, dict):
            key = user.pop("key", None)
            if key is None:
                raise KeyError("required 'key' in input dictionary")
        else:
            key = user.key
        # check if the user key already exists
        self._logger.info(f"checking if user '{key}' already exists")
        user_to_update = await get_user.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            key,
            client=self.client,
        )
        if user_to_update is not None:
            self._logger.info("user exists, updating it...")
            # if the user exists update it
            if isinstance(user, dict):
                json_body = UserUpdate.parse_obj(user)
            else:
                json_body = UserUpdate.parse_obj(user.dict(exclude={"key"}))
            updated_user = await update_user.asyncio(
                self.scope.project_id.hex,
                self.scope.environment_id.hex,
                key,
                json_body=json_body,
                client=self.client,
            )
            raise_for_error_by_action(
                updated_user, "user", json.dumps(json_body.dict()), "update"
            )
            return updated_user
        # otherwise create the user
        self._logger.info("user does not exist, creating it...")
        if isinstance(user, dict):
            json_body = UserCreate.parse_obj({**user, "key": key})
        else:
            json_body = user
        created_user = await create_user.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(
            created_user, "user", json.dumps(json_body.dict()), "create"
        )
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

    @property
    def api(self) -> PermitApiClient:
        return self
