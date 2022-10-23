from __future__ import annotations

from typing import Awaitable, Callable, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel

from permit.api.client import PermitApiClient
from permit.config import PermitConfig
from permit.openapi.models import (
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    RoleAssignmentRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    TenantCreate,
    TenantRead,
    TenantUpdate,
    UserCreate,
    UserRead,
)
from permit.utils.sync import async_to_sync, iscoroutine_func

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
    ...


class WriteOperation(Operation[Dict]):
    ...


class PermitSyncApiClient:
    def __init__(self, config: PermitConfig):
        self.config = config

    def __new__(cls, config: PermitConfig):
        async_api_instance = PermitApiClient(config=config)
        sync_api_instance = super(PermitSyncApiClient, cls).__new__(cls)
        for name in dir(sync_api_instance):
            if name.startswith("_"):
                # do not monkey-patch protected or private method
                continue
            if not hasattr(async_api_instance, name):
                # ensure that the async api class has the method
                continue
            attribute = getattr(async_api_instance, name)
            if callable(attribute) and iscoroutine_func(attribute):
                # monkey-patch public method using async_to_sync decorator
                setattr(sync_api_instance, name, async_to_sync(attribute))

        return sync_api_instance

    def get_user(self, user_key: str) -> UserRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def get_role(self, role_key: str) -> RoleRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def list_tenants(self, page: int = 1, per_page: int = 100) -> List[Tenant]:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def get_tenant(self, tenant_key: str) -> TenantRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def get_assigned_roles(
        self, user_key: str, tenant_key: Optional[str]
    ) -> List[RoleAssignmentRead]:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def get_resource(self, resource_key: str) -> ResourceRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def sync_user(self, user: Union[UserCreate, dict]) -> UserRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def delete_user(self, user_key: str) -> None:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def create_tenant(self, tenant: Union[TenantCreate, dict]) -> TenantRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def update_tenant(
        self, tenant_key: str, tenant: Union[TenantUpdate, dict]
    ) -> TenantRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def delete_tenant(self, tenant_key: str) -> None:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def delete_role(self, role_key: str) -> None:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def create_role(self, role: Union[RoleCreate, dict]) -> RoleRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def update_role(self, role_key: str, role: Union[RoleUpdate, dict]) -> RoleRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def assign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> RoleAssignmentRead:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def unassign_role(self, user_key: str, role_key: str, tenant_key: str) -> None:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def create_resource(self, resource: Union[ResourceCreate, dict]):
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def update_resource(self, resource_key: str, resource: Union[ResourceUpdate, dict]):
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    def delete_resource(self, resource_key: str):
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()

    @property
    def api(self) -> PermitSyncApiClient:
        return self
