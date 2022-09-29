from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import (
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    ParamSpec,
    TypeVar,
    Union,
)

from loguru import logger
from pydantic import BaseModel

from permit.config import PermitConfig
from permit.enforcement.interfaces import UserInput
from permit.exceptions import raise_for_error, raise_for_error_by_action
from permit.openapi import AuthenticatedClient
from permit.openapi.api.api_keys import get_api_key_scope
from permit.openapi.api.resources import (
    create_resource,
    delete_resource,
    get_resource,
    update_resource,
)
from permit.openapi.api.role_assignments import (
    assign_role,
    list_role_assignments,
    unassign_role,
)
from permit.openapi.api.roles import create_role, delete_role, get_role, update_role
from permit.openapi.api.tenants import (
    create_tenant,
    delete_tenant,
    get_tenant,
    list_tenants,
    update_tenant,
)
from permit.openapi.api.users import create_user, delete_user, get_user, update_user
from permit.openapi.models import (
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    TenantCreate,
    TenantRead,
    TenantUpdate,
    UserCreate,
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


class ReadApis(ABC):
    @abstractmethod
    async def get_user(self, user_key: str) -> UserRead:
        pass

    @abstractmethod
    async def get_role(self, role_key: str) -> RoleRead:
        pass

    @abstractmethod
    async def list_tenants(
        self,
        page: int = 1,
        per_page: int = 100,
    ) -> List[Tenant]:
        pass

    @abstractmethod
    async def get_tenant(self, tenant_key: str) -> TenantRead:
        pass

    @abstractmethod
    async def get_assigned_roles(
        self, user_key: str, tenant_key: Optional[str]
    ) -> List[RoleAssignmentRead]:
        pass

    @abstractmethod
    async def get_resource(self, resource_key: str) -> ResourceRead:
        pass


class WriteApis(ABC):
    @abstractmethod
    async def sync_user(self, user: Union[UserInput, dict]) -> UserRead:
        raise NotImplementedError("abstract class")

    @abstractmethod
    async def delete_user(self, user_key: str) -> None:
        raise NotImplementedError("abstract class")

    @abstractmethod
    async def create_tenant(self, tenant: Union[TenantCreate, dict]) -> TenantRead:
        raise NotImplementedError("abstract class")

    @abstractmethod
    async def update_tenant(
        self, tenant_key: str, tenant: Union[TenantUpdate, dict]
    ) -> TenantRead:
        raise NotImplementedError("abstract class")

    @abstractmethod
    async def delete_tenant(self, tenant_key: str) -> None:
        raise NotImplementedError("abstract class")

    @abstractmethod
    async def create_role(self, role: Union[RoleCreate, dict]) -> RoleRead:
        pass

    @abstractmethod
    async def update_role(
        self, role_key: str, role: Union[RoleUpdate, dict]
    ) -> RoleRead:
        pass

    @abstractmethod
    async def assign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> RoleAssignmentRead:
        raise NotImplementedError("abstract class")

    @abstractmethod
    async def unassign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> None:
        raise NotImplementedError("abstract class")

    @abstractmethod
    async def create_resource(self, resource: Union[ResourceCreate, dict]):
        pass

    @abstractmethod
    async def update_resource(
        self, resource_key: str, resource: Union[ResourceUpdate, dict]
    ):
        pass

    @abstractmethod
    async def delete_resource(self, resource_key: str):
        pass


class PermitApi(ReadApis, WriteApis, ABC):
    ...


P = ParamSpec("P")
RT = TypeVar("RT")


class PermitApiClient(PermitApi):
    def __init__(self, config: PermitConfig):
        self._config = config
        self._logger = logger.bind(name="permit.mutations.client")

        self.client = AuthenticatedClient(base_url=config.api_url, token=config.token)
        self.scope: APIKeyScopeRead | None = None

    @staticmethod
    def lazy_load_scope(func: Callable[P, RT]) -> Callable[P, Awaitable[RT]]:
        async def wrapper(
            self: PermitApiClient, *args: P.args, **kwargs: P.kwargs
        ) -> RT:
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

    # region read api ----------------------------------------------------------------

    @lazy_load_scope
    async def get_user(self, user_key: str) -> UserRead:
        user = await get_user.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            user_key,
            client=self.client,
        )
        raise_for_error_by_action(user, "user", user_key)
        return user

    @lazy_load_scope
    async def get_role(self, role_key: str) -> RoleRead:
        role = await get_role.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            role_key,
            client=self.client,
        )
        raise_for_error_by_action(role, "role", role_key)
        return role

    @lazy_load_scope
    async def get_tenant(self, tenant_key: str) -> TenantRead:
        tenant = await get_tenant.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            tenant_key,
            client=self.client,
        )
        raise_for_error_by_action(tenant, "tenant", tenant_key)
        return tenant

    @lazy_load_scope
    async def get_assigned_roles(
        self,
        user_key: str,
        tenant_key: Optional[str],
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        role_assignments = await list_role_assignments.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            tenant=tenant_key,
            user=user_key,
            page=page,
            per_page=per_page,
            client=self.client,
        )
        raise_for_error_by_action(
            role_assignments,
            "role_assignments",
            f"user:{user_key}, tenant:{tenant_key}:",
        )
        return role_assignments

    @lazy_load_scope
    async def get_resource(self, resource_key: str) -> ResourceRead:
        resource = await get_resource.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            resource_key,
            client=self.client,
        )
        raise_for_error_by_action(resource, "resource", resource_key)
        return resource

    # endregion
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
    async def delete_user(self, user_key: str) -> None:
        res = await delete_user.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            user_key,
            client=self.client,
        )
        raise_for_error_by_action(res, "user", user_key, "delete")

    @lazy_load_scope
    async def list_tenants(self, page: int = 1, per_page: int = 100) -> List[Tenant]:
        tenants = await list_tenants.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            page=page,
            per_page=per_page,
            client=self.client,
        )
        raise_for_error_by_action(tenants, "list", "tenants")
        return tenants

    @lazy_load_scope
    async def create_tenant(self, tenant: Union[TenantCreate, dict]) -> TenantRead:
        if isinstance(tenant, dict):
            json_body = TenantCreate.parse_obj(tenant)
        else:
            json_body = tenant
        created_tenant = await create_tenant.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(
            tenant, "tenant", json.dumps(json_body.dict()), "create"
        )
        return created_tenant

    @lazy_load_scope
    async def update_tenant(
        self, tenant_key: str, tenant: Union[TenantUpdate, dict]
    ) -> TenantRead:
        if isinstance(tenant, dict):
            json_body = TenantUpdate.parse_obj(tenant)
        else:
            json_body = tenant
        updated_tenant = await update_tenant.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            tenant_key,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(
            tenant, "tenant", json.dumps(json_body.dict()), "update"
        )
        return updated_tenant

    @lazy_load_scope
    async def delete_tenant(self, tenant_key: str) -> None:
        res = await delete_tenant.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            tenant_key,
            client=self.client,
        )
        raise_for_error_by_action(res, "tenant", tenant_key, "delete")

    @lazy_load_scope
    async def create_role(self, role: Union[RoleCreate, dict]) -> RoleRead:
        if isinstance(role, dict):
            json_body = RoleCreate.parse_obj(role)
        else:
            json_body = role
        role = await create_role.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(role, "role", json.dumps(json_body.dict()), "create")
        return role

    @lazy_load_scope
    async def update_role(
        self, role_key: str, role: Union[RoleUpdate, dict]
    ) -> RoleRead:
        if isinstance(role, dict):
            json_body = TenantUpdate.parse_obj(role)
        else:
            json_body = role
        updated_role = await update_role.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            role_key,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(role, "role", json.dumps(json_body.dict()), "update")
        return updated_role

    @lazy_load_scope
    async def assign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> RoleAssignmentRead:
        json_body = RoleAssignmentCreate(
            role=role_key, tenant=tenant_key, user=user_key
        )
        role_assignment = await assign_role.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(
            role_assignment, "role_assignment", json.dumps(json_body.dict()), "create"
        )
        return role_assignment

    @lazy_load_scope
    async def unassign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> None:
        json_body = RoleAssignmentRemove(
            role=role_key, tenant=tenant_key, user=user_key
        )
        unassigned_role = await unassign_role.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(
            unassigned_role,
            "role_assignment",
            f"user:{user_key}, role:{role_key}, tenant:{tenant_key}",
            "delete",
        )

    @lazy_load_scope
    async def delete_role(self, role_key: str):
        res = await delete_role.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            role_key,
            client=self.client,
        )
        raise_for_error_by_action(res, "role", role_key, "delete")

    @lazy_load_scope
    async def create_resource(
        self, resource: Union[ResourceCreate, dict]
    ) -> ResourceRead:
        if isinstance(resource, dict):
            json_body = ResourceCreate.parse_obj(resource)
        else:
            json_body = resource
        created_tenant = await create_resource.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(
            resource, "resource", json.dumps(json_body.dict()), "create"
        )
        return created_tenant

    @lazy_load_scope
    async def update_resource(
        self, resource_key: str, resource: Union[ResourceUpdate, dict]
    ) -> ResourceRead:
        if isinstance(resource, dict):
            json_body = ResourceUpdate.parse_obj(resource)
        else:
            json_body = resource
        updated_resource = await update_resource.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            resource_key,
            json_body=json_body,
            client=self.client,
        )
        raise_for_error_by_action(
            resource, "resource", json.dumps(json_body.dict()), "update"
        )
        return updated_resource

    @lazy_load_scope
    async def delete_resource(self, resource_key: str):
        res = await delete_resource.asyncio(
            self.scope.project_id.hex,
            self.scope.environment_id.hex,
            resource_key,
            client=self.client,
        )
        raise_for_error_by_action(res, "resource", resource_key, "delete")

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
    def api(self) -> PermitApi:
        return self
