from typing import List, Optional

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments  # type: ignore

from ..config import PermitConfig
from .base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
    required_context,
    required_permissions,
)
from .context import ApiContextLevel, ApiKeyAccessLevel
from .models import (
    BulkRoleAssignmentReport,
    BulkRoleUnAssignmentReport,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
)


class RoleAssignmentsApi(BasePermitApi):
    @property
    def __role_assignments(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/role_assignments".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def list(
        self,
        user_key: Optional[str] = None,
        role_key: Optional[str] = None,
        tenant_key: Optional[str] = None,
        resource_instance_key: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        """
        Retrieves a list of role assignments based on the specified filters.

        Args:
            user_key: if specified, only role granted to this user will be fetched.
            role_key: if specified, only assignments of this role will be fetched.
            tenant_key: (for roles) if specified, only role granted within this tenant will be fetched.
            resource_instance_key: (for resource roles) if specified, only roles granted with this instance as the object will be fetched.
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
        if resource_instance_key is not None:
            params.update(dict(resource_instance=resource_instance_key))
        return await self.__role_assignments.get(
            "",
            model=List[RoleAssignmentRead],
            params=params,
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def assign(self, assignment: RoleAssignmentCreate) -> RoleAssignmentRead:
        """
        Assigns a role to a user in the scope of a given tenant.

        Args:
            assignment: The role assignment details.

        Returns:
            the assigned role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__role_assignments.post(
            "", model=RoleAssignmentRead, json=assignment
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def unassign(self, unassignment: RoleAssignmentRemove) -> None:
        """
        Unassigns a role from a user in the scope of a given tenant.

        Args:
            unassignment: The role unassignment details.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__role_assignments.delete("", json=unassignment)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def bulk_assign(
        self, assignments: List[RoleAssignmentCreate]
    ) -> BulkRoleAssignmentReport:
        """
        Assigns multiple roles in bulk using the provided role assignments data.
        Each role assignment is a tuple of (user, role, tenant).

        Args:
            assignments: The role assignments to be performed in bulk.

        Returns:
            the bulk assignment report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__role_assignments.post(
            "/bulk",
            model=BulkRoleAssignmentReport,
            json=[assignment for assignment in assignments],
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def bulk_unassign(
        self, unassignments: List[RoleAssignmentRemove]
    ) -> BulkRoleUnAssignmentReport:
        """
        Removes multiple role assignments in bulk using the provided unassignment data.
        Each role to unassign is a tuple of (user, role, tenant).

        Args:
            unassignments: The role unassignments to be performed in bulk.

        Returns:
            the bulk unassignment report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__role_assignments.delete(
            "/bulk",
            model=BulkRoleUnAssignmentReport,
            json=[unassignment for unassignment in unassignments],
        )
