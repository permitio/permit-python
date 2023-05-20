from typing import List
from loguru import logger
from permit.api.base import BasePermitApi

from permit.api.models import RoleCreate, RoleRead, RoleUpdate
from permit.config import PermitConfig

class RolesApi(BasePermitApi):
    """
    Represents the interface for managing roles.
    """

    def __init__(self, config: PermitConfig):
        super().__init__(config)
    
    def list(self, page: int, per_page: int) -> List[RoleRead]:
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
        pass

    def get(self, roleKey: str) -> RoleRead:
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
        pass

    def getByKey(self, roleKey: str) -> RoleRead:
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
        pass

    def getById(self, roleId: str) -> RoleRead:
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
        pass

    def create(self, roleData: RoleCreate) -> RoleRead:
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
        pass

    def update(self, roleKey: str, roleData: RoleUpdate) -> RoleRead:
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
        pass

    def delete(self, roleKey: str) -> None:
        """
        Deletes a role.

        Args:
            roleKey: The key of the role to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        pass

    def assignPermissions(self, roleKey: str, permissions: List[str]) -> RoleRead:
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
        pass

    def removePermissions(self, roleKey: str, permissions: List[str]) -> RoleRead:
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
        pass