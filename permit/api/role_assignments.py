from typing import List, Optional

from permit.api.base import BasePermitApi, ensure_context, pagination_params
from permit.api.context import ApiKeyLevel
from permit.api.models import (
    BulkRoleAssignmentReport,
    BulkRoleUnAssignmentReport,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
)
from permit.config import PermitConfig


class RoleAssignmentsApi(BasePermitApi):
    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__role_assignments = self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/role_assignments".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def list(
        self,
        user_key: Optional[str] = None,
        tenant_key: Optional[str] = None,
        role_key: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        """
        Retrieves a list of role assignments based on the specified filters.

        Args:
            user_key: if specified, only role granted to this user will be fetched.
            tenant_key: if specified, only role granted within this tenant will be fetched.
            role_key: if specified, only assignments of this role will be fetched.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of role assignments.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__role_assignments.get(
            "",
            model=List[RoleAssignmentRead],
            params=dict(
                user=user_key,
                tenant=tenant_key,
                role=role_key,
                **pagination_params(page, per_page)
            ),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
            "", model=RoleAssignmentRead, json=assignment.dict()
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def unassign(self, unassignment: RoleAssignmentRemove) -> None:
        """
        Unassigns a role from a user in the scope of a given tenant.

        Args:
            unassignment: The role unassignment details.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__role_assignments.delete("", json=unassignment.dict())

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
            "",
            model=BulkRoleAssignmentReport,
            json=[assignment.dict() for assignment in assignments],
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
        return await self.__role_assignments.post(
            "",
            model=BulkRoleUnAssignmentReport,
            json=[unassignment.dict() for unassignment in unassignments],
        )
