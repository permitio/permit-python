from typing import List, Optional

from permit import PYDANTIC_VERSION
from permit.api.base import SimpleHttpClient
from permit.pdp_api.base import BasePdpPermitApi, pagination_params
from permit.pdp_api.models import RoleAssignment

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments  # type: ignore


class RoleAssignmentsApi(BasePdpPermitApi):
    @property
    def __role_assignments(self) -> SimpleHttpClient:
        return self._build_http_client("/local/role_assignments")

    @validate_arguments
    async def list(
        self,
        user_key: Optional[str] = None,
        role_key: Optional[str] = None,
        tenant_key: Optional[str] = None,
        resource_key: Optional[str] = None,
        resource_instance_key: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignment]:
        """
        Retrieves a list of role assignments based on the specified filters.

        Args:
            user_key: optional user filter, will only return role assignments granted to this user.
            role_key: optional role filter, will only return role assignments granting this role.
            tenant_key: optional tenant filter, will only return role assignments granted in that tenant.
            resource_key: optional resource type filter, will only return role assignments granted on that resource type.
            resource_instance_key: optional resource instance filter, will only return role assignments granted on that resource instance.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of role assignments.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        params = pagination_params(page, per_page)
        if user_key is not None:
            params.update(dict(user=user_key))
        if role_key is not None:
            params.update(dict(role=role_key))
        if tenant_key is not None:
            params.update(dict(tenant=tenant_key))
        if resource_key is not None:
            params.update(dict(resource=resource_key))
        if resource_instance_key is not None:
            params.update(dict(resource_instance=resource_instance_key))
        return await self.__role_assignments.get(
            "",
            model=List[RoleAssignment],
            params=params,
        )
