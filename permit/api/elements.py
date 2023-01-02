from __future__ import annotations

import json
from typing import List, Optional, Union
from uuid import UUID

from permit import PermitConfig
from permit.api.client import PermitBaseApi, lazy_load_scope
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.authentication import elements_login_as
from permit.openapi.models import UserLoginRequest, UserLoginResponse
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


class Elements(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,
        scope: Optional[APIKeyScopeRead],
    ):
        super().__init__(client=client, config=config, scope=scope)

    @lazy_load_scope
    async def login_as(
        self, user_id: str | UUID, tenant_id: str | UUID
    ) -> UserLoginResponse:
        if isinstance(user_id, UUID):
            user_id = user_id.hex
        if isinstance(tenant_id, UUID):
            tenant_id = tenant_id.hex

        payload = UserLoginRequest(
            user_id=user_id,
            tenant_id=tenant_id,
        )

        response = await elements_login_as.asyncio(
            json_body=payload,
            client=self._client,
        )
        raise_for_error_by_action(response, "login_request", payload.json())
        return response
