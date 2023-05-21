from typing import List

from pydantic import validate_arguments

from ..config import PermitConfig
from .base import BasePermitApi, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import (
    AddRolePermissions,
    RemoveRolePermissions,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)


class RolesApi(BasePermitApi):
    """
    Represents the interface for managing roles.
    """

    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__roles = self._build_http_client(
            "/v2/schema/{proj_id}/{env_id}/roles".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> List[RoleRead]:
        """
        Retrieves a list of roles.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            A list of roles.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.get(
            "", model=List[RoleRead], params=pagination_params(page, per_page)
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get(self, role_key: str) -> RoleRead:
        """
        Retrieves a role by its key.

        Args:
            role_key: The key of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.get(f"/{role_key}", model=RoleRead)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_key(self, role_key: str) -> RoleRead:
        """
        Retrieves a role by its key.
        Alias for the get method.

        Args:
            role_key: The key of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(role_key)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_id(self, role_id: str) -> RoleRead:
        """
        Retrieves a role by its ID.
        Alias for the get method.

        Args:
            role_id: The ID of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(role_id)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def create(self, role_data: RoleCreate) -> RoleRead:
        """
        Creates a new role.

        Args:
            role_data: The data for the new role.

        Returns:
            The created role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.post("", model=RoleRead, json=role_data.dict())

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def update(self, role_key: str, role_data: RoleUpdate) -> RoleRead:
        """
        Updates a role.

        Args:
            role_key: The key of the role.
            role_data: The updated data for the role.

        Returns:
            The updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.patch(
            f"/{role_key}", model=RoleRead, json=role_data.dict()
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def delete(self, role_key: str) -> None:
        """
        Deletes a role.

        Args:
            role_key: The key of the role to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.delete(f"/{role_key}")

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def assign_permissions(
        self, role_key: str, permissions: List[str]
    ) -> RoleRead:
        """
        Assigns permissions to a role.

        Args:
            role_key: The key of the role.
            permissions: An array of permission keys (<resourceKey:actionKey>) to be assigned to the role.

        Returns:
            A RoleRead object representing the updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.post(
            f"/{role_key}/permissions",
            model=RoleRead,
            json=AddRolePermissions(permissions=permissions).dict(),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def remove_permissions(
        self, role_key: str, permissions: List[str]
    ) -> RoleRead:
        """
        Removes permissions from a role.

        Args:
            role_key: The key of the role.
            permissions: An array of permission keys (<resourceKey:actionKey>) to be removed from the role.

        Returns:
            A RoleRead object representing the updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.delete(
            f"/{role_key}/permissions",
            model=RoleRead,
            json=RemoveRolePermissions(permissions=permissions).dict(),
        )
