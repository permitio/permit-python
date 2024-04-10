import json
from pprint import pformat
from typing import List, Optional, Union

import aiohttp
from loguru import logger
from permit_backend.schemas import RoleAssignmentRead

from ..config import PermitConfig
from ..exceptions import PermitConnectionError
from ..utils.context import Context, ContextStore
from ..utils.sync import SyncClass
from .base import pagination_params


class PdpApi:
    def __init__(self, config: PermitConfig):
        self._config = config
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {self._config.token}",
        }
        self._base_url = self._config.pdp

    async def list_role_assignments(
        self,
        user: Optional[str] = None,
        role: Optional[str] = None,
        tenant: Optional[str] = None,
        resource_instance: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> dict:
        """
        List all role assignments stored in the PDP.
        You can filter the results by specifying the query parameters.
            user: the user key to filter, will only return role assignments granted to this user.
            role: the role key to filter by, will only return role assignments of this role.
            tenant: the tenant key to filter by, will only return role assignments granted within this tenant.
            resource: the resource key to filter by, will only return role assignments granted on this resource.
            resource_instance: the resource instance key to filter by, will only return role assignments granted with this instance as the object.

        """

        url = f"{self._base_url}/local/role_assignments"
        params = pagination_params(page, per_page)

        if user is not None:
            params.update(dict(user=user))
        if role is not None:
            params.update(dict(role=role))
        if tenant is not None:
            params.update(dict(tenant=tenant))
        if resource_instance is not None:
            params.update(dict(resource_instance=resource_instance))

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._headers, params=params
            ) as response:
                if response.status != 200:
                    raise PermitConnectionError(
                        f"Failed to list role assignments: {response.status}"
                    )
            return await response.json()


class SyncEnforcer(PdpApi, metaclass=SyncClass):
    pass
