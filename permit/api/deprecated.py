from typing import List, Optional, Union
from uuid import UUID

from ..config import PermitConfig
from ..utils.deprecation import deprecated
from .base import BasePermitApi
from .elements import ElementsApi
from .models import (
    EmbeddedLoginRequestOutput,
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
from .role_assignments import RoleAssignmentsApi
from .roles import RolesApi
from .tenants import TenantsApi
from .users import UsersApi


class DeprecatedApi(BasePermitApi):
    """
    Represents the interface for managing roles.
    """

    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__resources = ResourcesApi(config)
        self.__role_assignments = RoleAssignmentsApi(config)
        self.__roles = RolesApi(config)
        self.__tenants = TenantsApi(config)
        self.__users = UsersApi(config)
        self.__elements = ElementsApi(config)

    @deprecated("use permit.api.users.get() instead")
    async def get_user(self, user_key: str) -> UserRead:
        return await self.__users.get(user_key)

    @deprecated("use permit.api.roles.get() instead")
    async def get_role(self, role_key: str) -> RoleRead:
        return await self.__roles.get(role_key)

    @deprecated("use permit.api.tenants.get() instead")
    async def get_tenant(self, tenant_key: str) -> TenantRead:
        return await self.__tenants.get(tenant_key)

    @deprecated("use permit.api.users.get_assigned_roles() instead")
    async def get_assigned_roles(
        self,
        user_key: str,
        tenant_key: Optional[str],
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        return await self.__users.get_assigned_roles(
            user_key, tenant=tenant_key, page=page, per_page=per_page
        )

    @deprecated("use permit.api.resources.get() instead")
    async def get_resource(self, resource_key: str) -> ResourceRead:
        return await self.__resources.get(resource_key)

    @deprecated("use permit.api.roles.list() instead")
    async def list_roles(self, page: int = 1, per_page: int = 100) -> List[RoleRead]:
        return await self.__roles.list(page=page, per_page=per_page)

    @deprecated("use permit.api.users.sync() instead")
    async def sync_user(self, user: Union[UserCreate, dict]) -> UserRead:
        return await self.__users.sync(user)

    @deprecated("use permit.api.users.delete() instead")
    async def delete_user(self, user_key: str) -> None:
        return await self.__users.delete(user_key)

    @deprecated("use permit.api.tenants.list() instead")
    async def list_tenants(
        self, page: int = 1, per_page: int = 100
    ) -> List[TenantRead]:
        return await self.__tenants.list(page=page, per_page=per_page)

    @deprecated("use permit.api.tenants.create() instead")
    async def create_tenant(self, tenant: Union[TenantCreate, dict]) -> TenantRead:
        tenant_data = (
            tenant if isinstance(tenant, TenantCreate) else TenantCreate(**tenant)
        )
        return await self.__tenants.create(tenant_data)

    @deprecated("use permit.api.tenants.update() instead")
    async def update_tenant(
        self, tenant_key: str, tenant: Union[TenantUpdate, dict]
    ) -> TenantRead:
        tenant_data = (
            tenant if isinstance(tenant, TenantUpdate) else TenantUpdate(**tenant)
        )
        return await self.__tenants.update(tenant_key, tenant_data)

    @deprecated("use permit.api.tenants.delete() instead")
    async def delete_tenant(self, tenant_key: str) -> None:
        return await self.__tenants.delete(tenant_key)

    @deprecated("use permit.api.roles.create() instead")
    async def create_role(self, role: Union[RoleCreate, dict]) -> RoleRead:
        role_data = role if isinstance(role, RoleCreate) else RoleCreate(**role)
        return await self.__roles.create(role_data)

    @deprecated("use permit.api.roles.update() instead")
    async def update_role(
        self, role_key: str, role: Union[RoleUpdate, dict]
    ) -> RoleRead:
        role_data = role if isinstance(role, RoleUpdate) else RoleUpdate(**role)
        return await self.__roles.update(role_key, role_data)

    @deprecated("use permit.api.users.assign_role() instead")
    async def assign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> RoleAssignmentRead:
        return await self.__role_assignments.assign(
            RoleAssignmentCreate(user=user_key, role=role_key, tenant=tenant_key)
        )

    @deprecated("use permit.api.users.unassign_role() instead")
    async def unassign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> None:
        return await self.__role_assignments.unassign(
            RoleAssignmentRemove(user=user_key, role=role_key, tenant=tenant_key)
        )

    @deprecated("use permit.api.roles.delete() instead")
    async def delete_role(self, role_key: str):
        return await self.__roles.delete(role_key)

    @deprecated("use permit.api.resources.create() instead")
    async def create_resource(
        self, resource: Union[ResourceCreate, dict]
    ) -> ResourceRead:
        resource_data = (
            resource
            if isinstance(resource, ResourceCreate)
            else ResourceCreate(**resource)
        )
        return await self.__resources.create(resource_data)

    @deprecated("use permit.api.resources.update() instead")
    async def update_resource(
        self, resource_key: str, resource: Union[ResourceUpdate, dict]
    ) -> ResourceRead:
        resource_data = (
            resource
            if isinstance(resource, ResourceUpdate)
            else ResourceUpdate(**resource)
        )
        return await self.__resources.update(resource_key, resource_data)

    @deprecated("use permit.api.resources.delete() instead")
    async def delete_resource(self, resource_key: str):
        return await self.__resources.delete(resource_key)

    @deprecated("use permit.elements.login_as() instead")
    async def elements_login_as(
        self, user_id: Union[str, UUID], tenant_id: Union[str, UUID]
    ) -> EmbeddedLoginRequestOutput:
        return await self.__elements.login_as(user_id=user_id, tenant_id=tenant_id)
