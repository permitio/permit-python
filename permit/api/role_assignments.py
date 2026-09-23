from typing import TYPE_CHECKING

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

import builtins

from permit.api.base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
)
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import (
    BulkRoleAssignmentReport,
    BulkRoleUnAssignmentReport,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
)


class RoleAssignmentsApi(BasePermitApi):
    """Assign roles to users and list or remove role assignments."""

    @property
    def __role_assignments(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/role_assignments", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/role_assignments"
        )

    @validate_arguments
    async def list(  # noqa: PLR0917 - public signature; callers may pass these positionally
        self,
        user_key: str | list[str] | None = None,
        role_key: str | list[str] | None = None,
        tenant_key: str | list[str] | None = None,
        resource_key: str | None = None,
        resource_instance_key: str | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[RoleAssignmentRead]:
        """Retrieves a list of role assignments based on the specified filters.

        Args:
            user_key: if specified, only role granted to this user will be fetched.
            role_key: if specified, only assignments of this role will be fetched.
            tenant_key: (for roles) if specified, only role granted within this tenant will be
                fetched.
            resource_key: (for resource roles) if specified, only roles granted on instances of this
                resource type will be fetched.
            resource_instance_key: (for resource roles) if specified, only roles granted with this
                instance as the object will be fetched. The instance identity, either
                `resource_type:instance_key` (like Repository:react) or the instance uuid; a bare
                instance key is rejected by the API with a 400.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of role assignments.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = list(pagination_params(page, per_page).items())
        if user_key is not None:
            if isinstance(user_key, list):
                params.extend(("user", user) for user in user_key)
            else:
                params.append(("user", user_key))
        if role_key is not None:
            if isinstance(role_key, list):
                params.extend(("role", role) for role in role_key)
            else:
                params.append(("role", role_key))
        if tenant_key is not None:
            if isinstance(tenant_key, list):
                params.extend(("tenant", tenant) for tenant in tenant_key)
            else:
                params.append(("tenant", tenant_key))
        if resource_key is not None:
            params.append(("resource", resource_key))
        if resource_instance_key is not None:
            params.append(("resource_instance", resource_instance_key))
        return await self.__role_assignments.get(
            "",
            model=list[RoleAssignmentRead],
            params=params,
        )

    @validate_arguments
    async def assign(self, assignment: RoleAssignmentCreate) -> RoleAssignmentRead:
        """Assigns a role to a user in the scope of a given tenant.

        Args:
            assignment: The role assignment details.

        Returns:
            the assigned role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__role_assignments.post("", model=RoleAssignmentRead, json=assignment)

    @validate_arguments
    async def unassign(self, unassignment: RoleAssignmentRemove) -> None:
        """Unassigns a role from a user in the scope of a given tenant.

        Args:
            unassignment: The role unassignment details.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__role_assignments.delete("", json=unassignment)

    @validate_arguments
    async def bulk_assign(
        self, assignments: builtins.list[RoleAssignmentCreate]
    ) -> BulkRoleAssignmentReport:
        """Assigns multiple roles in bulk using the provided role assignments data.

        Each role assignment is a tuple of (user, role, tenant).

        Args:
            assignments: The role assignments to be performed in bulk.

        Returns:
            the bulk assignment report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__role_assignments.post(
            "/bulk",
            model=BulkRoleAssignmentReport,
            json=list(assignments),
        )

    @validate_arguments
    async def bulk_unassign(
        self, unassignments: builtins.list[RoleAssignmentRemove]
    ) -> BulkRoleUnAssignmentReport:
        """Removes multiple role assignments in bulk using the provided unassignment data.

        Each role to unassign is a tuple of (user, role, tenant).

        Args:
            unassignments: The role unassignments to be performed in bulk.

        Returns:
            the bulk unassignment report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__role_assignments.delete(
            "/bulk",
            model=BulkRoleUnAssignmentReport,
            json=list(unassignments),
        )
