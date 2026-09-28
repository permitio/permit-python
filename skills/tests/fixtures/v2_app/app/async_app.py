"""A service that uses the async permit client, written against permit 2.x."""

from typing import Any, Dict, List, Optional

import httpx

from permit import PYDANTIC_VERSION, Permit, PermitConfig, UserUpdate
from permit.api.context import ApiKeyLevel
from permit.enforcement.interfaces import JWT, OpaResult

permit = Permit(PermitConfig(token="permit_key_example", pdp="http://localhost:7766"))
api = permit.api


async def load_user(key: str) -> Dict[str, Any]:
    user = await permit.api.get_user(key)
    return user.model_dump()


async def rename_tenant(key: str, name: str) -> None:
    await permit.api.update_tenant(key, tenant={"name": name})


async def grant(user: str, role: str, tenant: str) -> None:
    await permit.api.assign_role(user, role, tenant)


async def document_resource() -> object:
    return await api.get_resource("document")


async def update_names(key: str, first_name: Optional[str]) -> None:
    await permit.api.users.update(key, UserUpdate(email=None))
    await permit.api.users.update(key, UserUpdate(first_name=first_name))
    await permit.api.users.update(key, {"last_name": None})


async def relations(resource: str) -> List[object]:
    return await permit.api.resource_relations.list(resource)


async def status(url: str) -> int:
    async with httpx.AsyncClient() as client:
        return (await client.get(url)).status_code


def level_name() -> str:
    return ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY.value


def token_of(value: JWT) -> str:
    return value


def allowed(result: OpaResult) -> bool:
    return result.allow


def pydantic_major() -> int:
    return PYDANTIC_VERSION[0]
