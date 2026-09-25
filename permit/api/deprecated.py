from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from ..config import PermitConfig
from ..utils.deprecation import deprecated
from .base import BasePermitApi
from .elements import ElementsApi, EmbeddedLoginRequestOutput
from .models import (
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
)
from .resources import ResourcesApi
from .roles import RolesApi
from .tenants import TenantsApi
from .users import UsersApi


def _removal_notice(method: str, replacement: str) -> str:
    return f"permit.api.{method}() is deprecated and will be removed in permit 4.0; use {replacement}() instead."


class DeprecatedApi(BasePermitApi):
    """
    The flat methods on permit.api that predate the per-resource APIs.

    Each one warns and calls the method named in its warning. They will be removed in permit 4.0.
    """

    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__resources = ResourcesApi(config)
        self.__roles = RolesApi(config)
        self.__tenants = TenantsApi(config)
        self.__users = UsersApi(config)
        self.__elements = ElementsApi(config)

    @deprecated(_removal_notice("get_user", "permit.api.users.get"))
    async def get_user(self, user_key: str) -> UserRead:
        return await self.__users.get(user_key)

    @deprecated(_removal_notice("get_role", "permit.api.roles.get"))
    async def get_role(self, role_key: str) -> RoleRead:
        return await self.__roles.get(role_key)

    @deprecated(_removal_notice("get_tenant", "permit.api.tenants.get"))
    async def get_tenant(self, tenant_key: str) -> TenantRead:
        return await self.__tenants.get(tenant_key)

    @deprecated(_removal_notice("get_assigned_roles", "permit.api.users.get_assigned_roles"))
    async def get_assigned_roles(
        self,
        user_key: str,
        tenant_key: Optional[str],
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        return await self.__users.get_assigned_roles(user_key, tenant=tenant_key, page=page, per_page=per_page)

    @deprecated(_removal_notice("get_resource", "permit.api.resources.get"))
    async def get_resource(self, resource_key: str) -> ResourceRead:
        return await self.__resources.get(resource_key)

    @deprecated(_removal_notice("list_roles", "permit.api.roles.list"))
    async def list_roles(self, page: int = 1, per_page: int = 100) -> List[RoleRead]:
        return await self.__roles.list(page=page, per_page=per_page)

    @deprecated(_removal_notice("sync_user", "permit.api.users.sync"))
    async def sync_user(self, user: Union[UserCreate, Dict[str, Any]]) -> UserRead:
        return await self.__users.sync(user)

    @deprecated(_removal_notice("delete_user", "permit.api.users.delete"))
    async def delete_user(self, user_key: str) -> None:
        return await self.__users.delete(user_key)

    @deprecated(_removal_notice("list_tenants", "permit.api.tenants.list"))
    async def list_tenants(self, page: int = 1, per_page: int = 100) -> List[TenantRead]:
        return await self.__tenants.list(page=page, per_page=per_page)

    @deprecated(_removal_notice("create_tenant", "permit.api.tenants.create"))
    async def create_tenant(self, tenant: Union[TenantCreate, Dict[str, Any]]) -> TenantRead:
        tenant_data = tenant if isinstance(tenant, TenantCreate) else TenantCreate(**tenant)
        return await self.__tenants.create(tenant_data)

    @deprecated(_removal_notice("update_tenant", "permit.api.tenants.update"))
    async def update_tenant(self, tenant_key: str, tenant: Union[TenantUpdate, Dict[str, Any]]) -> TenantRead:
        tenant_data = tenant if isinstance(tenant, TenantUpdate) else TenantUpdate(**tenant)
        return await self.__tenants.update(tenant_key, tenant_data)

    @deprecated(_removal_notice("delete_tenant", "permit.api.tenants.delete"))
    async def delete_tenant(self, tenant_key: str) -> None:
        return await self.__tenants.delete(tenant_key)

    @deprecated(_removal_notice("create_role", "permit.api.roles.create"))
    async def create_role(self, role: Union[RoleCreate, Dict[str, Any]]) -> RoleRead:
        role_data = role if isinstance(role, RoleCreate) else RoleCreate(**role)
        return await self.__roles.create(role_data)

    @deprecated(_removal_notice("update_role", "permit.api.roles.update"))
    async def update_role(self, role_key: str, role: Union[RoleUpdate, Dict[str, Any]]) -> RoleRead:
        role_data = role if isinstance(role, RoleUpdate) else RoleUpdate(**role)
        return await self.__roles.update(role_key, role_data)

    @deprecated(_removal_notice("assign_role", "permit.api.users.assign_role"))
    async def assign_role(self, user_key: str, role_key: str, tenant_key: str) -> RoleAssignmentRead:
        return await self.__users.assign_role(RoleAssignmentCreate(user=user_key, role=role_key, tenant=tenant_key))

    @deprecated(_removal_notice("unassign_role", "permit.api.users.unassign_role"))
    async def unassign_role(self, user_key: str, role_key: str, tenant_key: str) -> None:
        return await self.__users.unassign_role(RoleAssignmentRemove(user=user_key, role=role_key, tenant=tenant_key))

    @deprecated(_removal_notice("delete_role", "permit.api.roles.delete"))
    async def delete_role(self, role_key: str) -> None:
        return await self.__roles.delete(role_key)

    @deprecated(_removal_notice("create_resource", "permit.api.resources.create"))
    async def create_resource(self, resource: Union[ResourceCreate, Dict[str, Any]]) -> ResourceRead:
        resource_data = resource if isinstance(resource, ResourceCreate) else ResourceCreate(**resource)
        return await self.__resources.create(resource_data)

    @deprecated(_removal_notice("update_resource", "permit.api.resources.update"))
    async def update_resource(self, resource_key: str, resource: Union[ResourceUpdate, Dict[str, Any]]) -> ResourceRead:
        resource_data = resource if isinstance(resource, ResourceUpdate) else ResourceUpdate(**resource)
        return await self.__resources.update(resource_key, resource_data)

    @deprecated(_removal_notice("delete_resource", "permit.api.resources.delete"))
    async def delete_resource(self, resource_key: str) -> None:
        return await self.__resources.delete(resource_key)

    @deprecated(_removal_notice("elements_login_as", "permit.elements.login_as"))
    async def elements_login_as(
        self, user_id: Union[str, UUID], tenant_id: Union[str, UUID]
    ) -> EmbeddedLoginRequestOutput:
        return await self.__elements.login_as(user_id=user_id, tenant_id=tenant_id)
