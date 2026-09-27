"""A script that uses the blocking permit client, written against permit 2.x."""

import asyncio
from typing import Any, Dict, List
from uuid import UUID

from permit.sync import Permit as SyncPermit
from permit.utils.context import ContextStore, ContextTransform

client = SyncPermit(token="permit_key_example", pdp="http://localhost:7766")
store = ContextStore()


def add_region(context: Dict[str, Any]) -> Dict[str, Any]:
    return {**context, "region": "eu"}


transform: ContextTransform = add_region
store.register_transform(transform)


async def who_can_read(document: str) -> List[str]:
    result = await client.authorized_users("read", f"document:{document}")
    return list(result.users)


async def permissions(user: str) -> Dict[str, Any]:
    return await client.get_user_permissions(user)


def visible(user: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return asyncio.run(client.filter_objects(user, "read", {}, documents))


def role_keys() -> List[str]:
    return [role.key for role in client.api.list_roles()]


def login(user_id: UUID, tenant_id: UUID) -> object:
    return client.api.elements_login_as(user_id, tenant_id)
