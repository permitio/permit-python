"""Import aliases the scanner has to follow, written against permit 2.x."""

import permit as p  # type: ignore[import-untyped]
import permit.sync as ps
from permit import Permit as P  # noqa: N817 - the short alias is what this fixture tests
from permit import sync

async_client = P(token="permit_key_example")
blocking = ps.Permit(token="permit_key_example")
other_blocking = sync.Permit(token="permit_key_example")


class Service:
    def __init__(self, client: P) -> None:
        self.permit = client

    async def tenant(self, key: str) -> object:
        return await self.permit.api.get_tenant(key)

    async def readers(self) -> object:
        return await self.permit.authorized_users("read", "document")


def blocking_readers() -> object:
    return blocking.authorized_users("read", "document")


async def awaited_blocking(user: str) -> object:
    return await other_blocking.get_user_permissions(user)


async def from_elsewhere(client: object) -> object:
    return await client.api.get_role("admin")


async def unknown_client(client: object) -> object:
    return await client.authorized_users("read", "document")


def pydantic_version() -> object:
    return p.PYDANTIC_VERSION


def first_level() -> object:
    return p.api.context.ApiKeyLevel.WAIT_FOR_INIT
