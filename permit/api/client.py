from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Dict, Generic, List, Optional, TypeVar, Union
from uuid import UUID

from loguru import logger
from pydantic import BaseModel
from typing_extensions import ParamSpec

from permit.api.tenants import Tenant
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error, raise_for_error_by_action
from permit.openapi import AuthenticatedClient
from permit.openapi.api.api_keys import get_api_key_scope
from permit.openapi.api.authentication import elements_login_as
from permit.openapi.api.resources import (
    create_resource,
    delete_resource,
    update_resource,
)
from permit.openapi.api.role_assignments import (
    assign_role,
    list_role_assignments,
    unassign_role,
)
from permit.openapi.api.users import create_user, get_user, update_user
from permit.openapi.models import (
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
    UserCreate,
    UserLoginRequest,
    UserLoginResponse,
    UserRead,
    UserUpdate,
)
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

    @lazy_load_scope
    async def elements_login_as(
        self, user_id: str | UUID, tenant_id: str | UUID
    ) -> UserLoginResponse:
        if isinstance(user_id, UUID):
            user_id = user_id.hex
        if isinstance(tenant_id, UUID):
            tenant_id = tenant_id.hex

        payload = UserLoginRequest(
            user_id=user_id,
            tenant_id=tenant_id,
        )

        response = await elements_login_as.asyncio(
            json_body=payload,
            client=self.client,
        )
        raise_for_error_by_action(response, "login_request", payload.json())
        return response

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
