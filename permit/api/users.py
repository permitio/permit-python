from typing import List, Optional, Union

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from .base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
)
from .context import ApiContextLevel, ApiKeyAccessLevel
from .models import (
    PaginatedResultUserRead,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
    UserCreate,
    UserCreateBulkOperation,
    UserCreateBulkOperationResult,
    UserDeleteBulkOperation,
    UserDeleteBulkOperationResult,
    UserRead,
    UserReplaceBulkOperation,
    UserReplaceBulkOperationResult,
    UserUpdate,
)


class UsersApi(BasePermitApi):
    @property
    def __users(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/users", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/users"
            )

    @property
    def __role_assignments(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/role_assignments", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/role_assignments"
            )

    @property
    def __bulk_operations(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/bulk/users", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/bulk/users"
            )

    @validate_arguments  # type: ignore[operator]
    async def list(self, page: int = 1, per_page: int = 100) -> PaginatedResultUserRead:
        """
        Retrieves a list of users.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            a paginated list of users.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.get(
            "",
            model=PaginatedResultUserRead,
            params=pagination_params(page, per_page),
        )

    async def _get(self, user_key: str) -> UserRead:
        return await self.__users.get(f"/{user_key}", model=UserRead)

    @validate_arguments  # type: ignore[operator]
    async def get(self, user_key: str) -> UserRead:
        """
        Retrieves a user by its key.

        Args:
            user_key: The key of the user.

        Returns:
            the user object.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(user_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_key(self, user_key: str) -> UserRead:
        """
        Retrieves a user by its key.
        Alias for the get method.

        Args:
            user_key: The key of the user.

        Returns:
            the user object.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(user_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_id(self, user_id: str) -> UserRead:
        """
        Retrieves a user by its ID.
        Alias for the get method.

        Args:
            user_id: The ID of the user.

        Returns:
            the user object.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(user_id)

    @validate_arguments  # type: ignore[operator]
    async def create(self, user_data: UserCreate) -> UserRead:
        """
        Creates a new user.

        Args:
            user_data: The data for the new user.

        Returns:
            the created user.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.post("", model=UserRead, json=user_data)

    @validate_arguments  # type: ignore[operator]
    async def update(self, user_key: str, user_data: UserUpdate) -> UserRead:
        """
        Updates a user.

        Args:
            user_key: The key of the user.
            user_data: The updated data for the user.

        Returns:
            the updated user.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.patch(f"/{user_key}", model=UserRead, json=user_data)

    @validate_arguments  # type: ignore[operator]
    async def sync(self, user: Union[UserCreate, dict]) -> UserRead:
        """
        Synchronizes user data by creating or updating a user.

        Args:
            user: The data of the user to be synchronized.

        Returns:
            the result of the user creation or update operation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        if isinstance(user, dict):
            user_key = user.pop("key", None)
            if user_key is None:
                raise KeyError("required 'key' in input dictionary")
        else:
            user_key = user.key
        return await self.__users.put(f"/{user_key}", model=UserRead, json=user)

    @validate_arguments  # type: ignore[operator]
    async def delete(self, user_key: str) -> None:
        """
        Deletes a user.

        Args:
            user_key: The key of the user to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.delete(f"/{user_key}")

    @validate_arguments  # type: ignore[operator]
    async def bulk_create(self, users: List[UserCreate]) -> UserCreateBulkOperationResult:
        """
        Creates users in bulk.

        Args:
            users: The users to create

        Returns:
            the bulk creation report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.post(
            "",
            model=UserCreateBulkOperationResult,
            json=UserCreateBulkOperation(operations=users),
        )

    @validate_arguments  # type: ignore[operator]
    async def bulk_replace(self, users: List[UserCreate]) -> UserReplaceBulkOperationResult:
        """
        Replaces users in bulk.

        If the user exists - replaces it.
        Otherwise, creates previously non-existing users.

        Args:
            users: The users to replace.

        Returns:
            the bulk replace report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.put(
            "",
            model=UserReplaceBulkOperationResult,
            json=UserReplaceBulkOperation(operations=users),
        )

    @validate_arguments  # type: ignore[operator]
    async def bulk_delete(self, users: List[str]) -> UserDeleteBulkOperationResult:
        """
        Deletes users in bulk.

        Args:
            users: The users identities to delete. Each identity can be either the user key or the user id.

        Returns:
            the bulk delete report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.delete(
            "",
            model=UserDeleteBulkOperationResult,
            json=UserDeleteBulkOperation(idents=users),
        )

    @validate_arguments  # type: ignore[operator]
    async def assign_role(self, assignment: RoleAssignmentCreate) -> RoleAssignmentRead:
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.post(
            f"/{assignment.user}/roles",
            model=RoleAssignmentRead,
            json=assignment.dict(exclude={"user"}),
        )

    @validate_arguments  # type: ignore[operator]
    async def unassign_role(self, unassignment: RoleAssignmentRemove) -> None:
        """
        Unassigns a role from a user in the scope of a given tenant.

        Args:
            unassignment: The role unassignment details.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.delete(
            f"/{unassignment.user}/roles",
            json=unassignment.dict(exclude={"user"}),
        )

    @validate_arguments  # type: ignore[operator]
    async def get_assigned_roles(
        self,
        user: str,
        tenant: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        """
        Retrieves the roles assigned to a user in a given tenant (if the tenant filter is provided)
        or across all tenants (if the tenant filter is not provided).

        Args:
            user: The key of the user.
            tenant: The key of the tenant.
            page: The page number to fetch.
            per_page: How many items to fetch per page.

        Returns:
            an array of role assignments for the user.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = pagination_params(page, per_page)
        params.update({"user": user})
        if tenant is not None:
            params.update({"tenant": tenant})
        return await self.__role_assignments.get(
            "",
            model=List[RoleAssignmentRead],
            params=params,
        )
