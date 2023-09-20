from typing import List, Optional, Union

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments  # type: ignore

from .base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
    required_context,
    required_permissions,
)
from .context import ApiContextLevel, ApiKeyAccessLevel
from .models import (
    PaginatedResultUserRead,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
    UserCreate,
    UserRead,
    UserUpdate,
)


class UsersApi(BasePermitApi):
    @property
    def __users(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/users".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

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
        return await self.__users.get(
            "",
            model=PaginatedResultUserRead,
            params=pagination_params(page, per_page),
        )

    async def _get(self, user_key: str) -> UserRead:
        return await self.__users.get(f"/{user_key}", model=UserRead)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        return await self._get(user_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        return await self._get(user_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        return await self._get(user_id)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        return await self.__users.post("", model=UserRead, json=user_data)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        return await self.__users.patch(f"/{user_key}", model=UserRead, json=user_data)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        if isinstance(user, dict):
            user_key = user.pop("key", None)
            if user_key is None:
                raise KeyError("required 'key' in input dictionary")
        else:
            user_key = user.key
        return await self.__users.put(f"/{user_key}", model=UserRead, json=user)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def delete(self, user_key: str) -> None:
        """
        Deletes a user.

        Args:
            user_key: The key of the user to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__users.delete(f"/{user_key}")

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        return await self.__users.post(
            f"/{assignment.user}/roles",
            model=RoleAssignmentRead,
            json=assignment.dict(exclude={"user"}),
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def unassign_role(self, unassignment: RoleAssignmentRemove) -> None:
        """
        Unassigns a role from a user in the scope of a given tenant.

        Args:
            unassignment: The role unassignment details.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__users.delete(
            f"/{unassignment.user}/roles",
            json=unassignment.dict(exclude={"user"}),
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
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
        params = pagination_params(page, per_page)
        params.update({"user": user})
        if tenant is not None:
            params.update({"tenant": tenant})
        return await self.__role_assignments.get(
            "",
            model=List[RoleAssignmentRead],
            params=params,
        )
