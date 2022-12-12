from __future__ import annotations

from typing import TYPE_CHECKING, Tuple
from uuid import UUID

if TYPE_CHECKING:
    from permit.client import Permit


class PermitElements:
    def __init__(self, client: Permit):
        self._client = client

    async def login_as(
        self, user_id: str | UUID, tenant_id: str | UUID
    ) -> Tuple[str, str]:
        ticket = await self._client.api.elements_login_as(user_id, tenant_id)
        return ticket.token, ticket.redirect_url
