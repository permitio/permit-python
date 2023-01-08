from __future__ import annotations

import json
from typing import List, Optional, Union
from uuid import UUID

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
    async def get(self, tenant_key: str) -> TenantRead:
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
        return await self.get(tenant_key)

    @lazy_load_context
    async def get_by_id(self, tenant_id: UUID) -> TenantRead:
        return await self.get(tenant_id.hex)

    @lazy_load_context
    async def list(self, page: int = 1, per_page: int = 100) -> List[TenantRead]:
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
    async def create(self, tenant: Union[TenantCreate, dict]) -> TenantRead:
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
        res = await delete_tenant.asyncio(
            self._config.context.project,
            self._config.context.environment,
            tenant_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "tenant", tenant_key, "delete")
