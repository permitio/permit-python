from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from permit.openapi.models.user_login_response import UserLoginAsResponse

if TYPE_CHECKING:
    from permit.client import Permit


class LoginAsErrorMessages(str, Enum):
    USER_NOT_FOUND = "User not found"
    TENANT_NOT_FOUND = "Tenant not found"
    INVALID_PERMISSION_LEVEL = "Invalid user permission level"
    FORBIDDEN_ACCESS = "Forbidden access"


class PermitElements:
    def __init__(self, client: Permit):
        self._client = client

    async def login_as(
        self, user_id: str | UUID, tenant_id: str | UUID
    ) -> UserLoginAsResponse:
        ticket = await self._client.api.elements_login_as(user_id, tenant_id)
        return UserLoginAsResponse(
            **ticket.dict(),
            content={"url": ticket.redirect_url})