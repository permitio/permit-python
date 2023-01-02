from __future__ import annotations

import json
from typing import List, Optional, Union
from uuid import UUID

from permit import PermitConfig
from permit.api.client import PermitBaseApi, lazy_load_scope
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.tenants import (
    create_tenant,
    delete_tenant,
    get_tenant,
    list_tenants,
    update_tenant,
)
from permit.openapi.models import TenantCreate, TenantRead, TenantUpdate
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


class Tenant(PermitBaseApi):
    def __init__(self, client, config: PermitConfig, scope: Optional[APIKeyScopeRead]):
        super().__init__(config=config, scope=scope, client=client)

    # CRUD Methods
    @lazy_load_scope
    async def get(self, tenant_key: str) -> TenantRead:
        tenant = await get_tenant.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            tenant_key,
            client=self._client,
        )
        raise_for_error_by_action(tenant, "tenant", tenant_key)
        return tenant

    @lazy_load_scope
    async def get_by_key(self, tenant_key: str) -> TenantRead:
        return await self.get(tenant_key)

    @lazy_load_scope
    async def get_by_id(self, tenant_id: UUID) -> TenantRead:
        return await self.get(tenant_id.hex)

    @lazy_load_scope
    async def list(self, page: int = 1, per_page: int = 100) -> List[TenantRead]:
        tenants = await list_tenants.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(tenants, "list", "tenants")
        return tenants

    @lazy_load_scope
    async def create(self, tenant: Union[TenantCreate, dict]) -> TenantRead:
        if isinstance(tenant, dict):
            json_body = TenantCreate.parse_obj(tenant)
        else:
            json_body = tenant
        created_tenant = await create_tenant.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            tenant, "tenant", json.dumps(json_body.dict()), "create"
        )
        return created_tenant

    @lazy_load_scope
    async def update(
        self, tenant_key: str, tenant: Union[TenantUpdate, dict]
    ) -> TenantRead:
        if isinstance(tenant, dict):
            json_body = TenantUpdate.parse_obj(tenant)
        else:
            json_body = tenant
        updated_tenant = await update_tenant.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            tenant_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            tenant, "tenant", json.dumps(json_body.dict()), "update"
        )
        return updated_tenant

    @lazy_load_scope
    async def delete(self, tenant_key: str) -> None:
        res = await delete_tenant.asyncio(
            self._scope.project_id.hex,
            self._scope.environment_id.hex,
            tenant_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "tenant", tenant_key, "delete")
