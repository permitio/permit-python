from typing import List

from loguru import logger

from permit.api.base import BasePermitApi, ensure_context
from permit.api.context import ApiKeyLevel
from permit.api.models import (
    AddRolePermissions,
    RemoveRolePermissions,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)
from permit.config import PermitConfig


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
    async def list(self, page: int = 1, per_page: int = 100) -> List[RoleRead]:
        """
        Retrieves a list of roles.

        Args:
            pagination: The pagination options.

        Returns:
            A list of roles.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.get(
            "", model=List[RoleRead], params={"page": page, "per_page": per_page}
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def get(self, roleKey: str) -> RoleRead:
        """
        Retrieves a role by its key.

        Args:
            roleKey: The key of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.get(f"/{roleKey}", model=RoleRead)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def getByKey(self, roleKey: str) -> RoleRead:
        """
        Retrieves a role by its key.
        Alias for the get method.

        Args:
            roleKey: The key of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(roleKey)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def getById(self, roleId: str) -> RoleRead:
        """
        Retrieves a role by its ID.
        Alias for the get method.

        Args:
            roleId: The ID of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(roleId)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def create(self, roleData: RoleCreate) -> RoleRead:
        """
        Creates a new role.

        Args:
            roleData: The data for the new role.

        Returns:
            The created role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.post("", model=RoleRead, json=roleData.dict())

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def update(self, roleKey: str, roleData: RoleUpdate) -> RoleRead:
        """
        Updates a role.

        Args:
            roleKey: The key of the role.
            roleData: The updated data for the role.

        Returns:
            The updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.patch(
            f"/{roleKey}", model=RoleRead, json=roleData.dict()
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def delete(self, roleKey: str) -> None:
        """
        Deletes a role.

        Args:
            roleKey: The key of the role to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.delete(f"/{roleKey}")

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def assignPermissions(self, roleKey: str, permissions: List[str]) -> RoleRead:
        """
        Assigns permissions to a role.

        Args:
            roleKey: The key of the role.
            permissions: An array of permission keys (<resourceKey:actionKey>) to be assigned to the role.

        Returns:
            A RoleRead object representing the updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.post(
            f"/{roleKey}/permissions",
            model=RoleRead,
            json=AddRolePermissions(permissions=permissions).dict(),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def removePermissions(self, roleKey: str, permissions: List[str]) -> RoleRead:
        """
        Removes permissions from a role.

        Args:
            roleKey: The key of the role.
            permissions: An array of permission keys (<resourceKey:actionKey>) to be removed from the role.

        Returns:
            A RoleRead object representing the updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__roles.delete(
            f"/{roleKey}/permissions",
            model=RoleRead,
            json=RemoveRolePermissions(permissions=permissions).dict(),
        )
