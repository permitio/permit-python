"""The service in v2_app/app/async_app.py, migrated to permit 3.0.0."""

from typing import Any, Dict, List, Optional

import httpx
from pydantic.v1 import BaseModel

from permit import Permit, PermitConfig, UserUpdate
from permit.api.context import ApiKeyAccessLevel
from permit.api.models import RelationRead
from permit.utils.pydantic_version import PYDANTIC_VERSION

permit = Permit(PermitConfig(token="permit_key_example", pdp="http://localhost:7766"))
api = permit.api


class OpaResult(BaseModel):
    allow: bool


async def load_user(key: str) -> Dict[str, Any]:
    user = await permit.api.users.get(key)
    return user.dict()


async def rename_tenant(key: str, name: str) -> None:
    await permit.api.tenants.update(key, tenant_data={"name": name})


async def grant(user: str, role: str, tenant: str) -> None:
    await permit.api.users.assign_role({"user": user, "role": role, "tenant": tenant})


async def document_resource() -> object:
    return await api.resources.get("document")


async def update_names(key: str, first_name: Optional[str]) -> None:
    if first_name is not None:
        await permit.api.users.update(key, UserUpdate(first_name=first_name))


async def relations(resource: str) -> List[RelationRead]:
    page = await permit.api.resource_relations.list(resource)
    return page.data


async def status(url: str) -> int:
    async with httpx.AsyncClient() as client:
        return (await client.get(url)).status_code


def level_name() -> str:
    return ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY.value


def token_of(value: str) -> str:
    return value


def allowed(result: OpaResult) -> bool:
    return result.allow


def pydantic_major() -> int:
    return PYDANTIC_VERSION[0]
