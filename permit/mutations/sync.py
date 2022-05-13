import asyncio
from typing import Optional

from permit.enforcement.interfaces import UserInput
from permit.utils.sync import run_sync

from .client import PermitApiClient as AsyncPermitApiClient
from .client import Tenant


class PermitApiClient(AsyncPermitApiClient):
    def get_user(self, user_key: str):
        op = super().get_user(user_key=user_key)
        return run_sync(op.run())

    def get_role(self, role_key: str):
        op = super().get_role(role_key=role_key)
        return run_sync(op.run())

    def get_tenant(self, tenant_key: str):
        op = super().get_tenant(tenant_key=tenant_key)
        return run_sync(op.run())

    def get_assigned_roles(self, user_key: str, tenant_key: Optional[str]):
        op = super().get_assigned_roles(user_key=user_key, tenant_key=tenant_key)
        return run_sync(op.run())

    def sync_user(self, user: UserInput):
        op = super().sync_user(user=user)
        return run_sync(op.run())

    def delete_user(self, user_key: str):
        op = super().delete_user(user_key=user_key)
        return run_sync(op.run())

    def create_tenant(self, tenant: Tenant):
        op = super().create_tenant(tenant=tenant)
        return run_sync(op.run())

    def update_tenant(self, tenant: Tenant):
        op = super().update_tenant(tenant=tenant)
        return run_sync(op.run())

    def delete_tenant(self, tenant_key: str):
        op = super().delete_tenant(tenant_key=tenant_key)
        return run_sync(op.run())

    def assign_role(self, user_key: str, role_key: str, tenant_key: str):
        op = super().assign_role(
            user_key=user_key, role_key=role_key, tenant_key=tenant_key
        )
        return run_sync(op.run())

    def unassign_role(self, user_key: str, role_key: str, tenant_key: str):
        op = super().unassign_role(
            user_key=user_key, role_key=role_key, tenant_key=tenant_key
        )
        return run_sync(op.run())
