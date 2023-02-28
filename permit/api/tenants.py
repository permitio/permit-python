from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.tenants import (
    create_tenant,
    delete_tenant,
    get_tenant,
    list_tenants,
    update_tenant,
)
from permit.openapi.models import TenantCreate, TenantRead, TenantUpdate


class Tenant(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,
        logger: Logger,
    ):
        super().__init__(config=config, client=client, logger=logger)

    # CRUD Methods
    @lazy_load_context
    async def list(self, page: int = 1, per_page: int = 100) -> List[TenantRead]:
        """
        Lists the tenants from your context's environment.

        Usage Example:
            ```
            from permit import Permit, TenantRead
            permit = Permit(...)
            tenants: List[TenantRead] = await permit.api.tenants.list()
            ```
        """
        tenants = await list_tenants.asyncio(
            self._config.context.project,
            self._config.context.environment,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(tenants, "list", "tenants")
        return tenants

    @lazy_load_context
    async def get(self, tenant_key: str) -> TenantRead:
        """
        Gets a tenant for a given tenant key (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, TenantRead
            permit = Permit(...)
            tenant: TenantRead = await permit.api.tenants.get("default")
            ```
        """

        tenant = await get_tenant.asyncio(
            self._config.context.project,
            self._config.context.environment,
            tenant_key,
            client=self._client,
        )
        raise_for_error_by_action(tenant, "tenant", tenant_key)
        return tenant

    @lazy_load_context
    async def get_by_key(self, tenant_key: str) -> TenantRead:
        """
        Gets a tenant for a given tenant key (from your context's environment) - same as `get()` function.

        Usage Example:
            ```
            from permit import Permit, TenantRead
            permit = Permit(...)
            tenant: TenantRead = await permit.api.tenants.get_by_key("default")
            ```
        """
        return await self.get(tenant_key)

    @lazy_load_context
    async def get_by_id(self, tenant_id: UUID) -> TenantRead:
        """
        Gets a tenant for a given tenant id (from your context's environment).

        Usage Example:
            ```
            from permit import Permit, TenantRead
            permit = Permit(...)
            tenant: TenantRead = await permit.api.tenants.get_by_id(UUID("b310ff06-9a6a-4762-a038-55886525323d"))
            ```
        """
        return await self.get(tenant_id.hex)

    @lazy_load_context
    async def create(self, tenant: Union[TenantCreate, dict]) -> TenantRead:
        """
        Creates a tenant under the context's environment - can be either TenantCreate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, TenantRead, TenantCreate
            permit = Permit(...)
            tenant_create = TenantCreate(
                key="rnd",
                name="RnD",
                description="The R&D tenant",
                )
            tenant: TenantRead = await permit.api.tenants.create(tenant_create)
            ```
        """
        if isinstance(tenant, dict):
            json_body = TenantCreate.parse_obj(tenant)
        else:
            json_body = tenant
        created_tenant = await create_tenant.asyncio(
            self._config.context.project,
            self._config.context.environment,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            tenant, "tenant", json.dumps(json_body.dict()), "create"
        )
        return created_tenant

    @lazy_load_context
    async def update(
        self, tenant_key: str, tenant: Union[TenantUpdate, dict]
    ) -> TenantRead:
        """
        Updates a tenant under the context's environment - by a given tenant key -
        can be either TenantUpdate or a dictionary.

        Usage Example:
            ```
            from permit import Permit, TenantRead, TenantUpdate
            permit = Permit(...)
            tenant_update = TenantUpdate(
                name="RnD Team",
                description="The R&D tenant",
                )
            tenant: TenantRead = await permit.api.tenants.update("rnd", tenant_update)
            ```
        """
        if isinstance(tenant, dict):
            json_body = TenantUpdate.parse_obj(tenant)
        else:
            json_body = tenant
        updated_tenant = await update_tenant.asyncio(
            self._config.context.project,
            self._config.context.environment,
            tenant_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            tenant, "tenant", json.dumps(json_body.dict()), "update"
        )
        return updated_tenant

    @lazy_load_context
    async def delete(self, tenant_key: str) -> None:
        """
        Deletes a tenant under the context's environment - by a given tenant key.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.tenants.delete("rnd")
            ```
        """
        res = await delete_tenant.asyncio(
            self._config.context.project,
            self._config.context.environment,
            tenant_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "tenant", tenant_key, "delete")
