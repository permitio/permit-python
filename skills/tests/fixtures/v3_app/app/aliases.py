"""The aliases in v2_app/app/aliases.py, migrated to permit 3.0.0."""

import permit as p
import permit.sync as ps
from permit import Permit as P  # noqa: N817 - the short alias is what this fixture tests
from permit import sync
from permit.utils.pydantic_version import PYDANTIC_VERSION

async_client = P(token="permit_key_example")
blocking = ps.Permit(token="permit_key_example")
other_blocking = sync.Permit(token="permit_key_example")


class Service:
    def __init__(self, client: P) -> None:
        self.permit = client

    async def tenant(self, key: str) -> object:
        return await self.permit.api.tenants.get(key)

    async def readers(self) -> object:
        return await self.permit.authorized_users("read", "document")


def blocking_readers() -> object:
    return blocking.authorized_users("read", "document")


def blocking_permissions(user: str) -> object:
    return other_blocking.get_user_permissions(user)


async def from_elsewhere(client: P) -> object:
    return await client.api.roles.get("admin")


async def known_client(client: P) -> object:
    return await client.authorized_users("read", "document")


def pydantic_version() -> object:
    return PYDANTIC_VERSION


def first_level() -> object:
    return p.api.context.ApiKeyAccessLevel.WAIT_FOR_INIT
