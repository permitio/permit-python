from typing import List

from pydantic import validate_arguments

from ..config import PermitConfig
from .base import BasePermitApi, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import ProjectCreate, ProjectRead, ProjectUpdate


class ProjectsApi(BasePermitApi):
    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__projects = self._build_http_client("/v2/projects")

    @ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> List[ProjectRead]:
        """
        Retrieves a list of projects.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            A promise that resolves to an array of projects.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__projects.get(
            "", model=List[ProjectRead], params=pagination_params(page, per_page)
        )

    @ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    @validate_arguments
    async def get(self, project_key: str) -> ProjectRead:
        """
        Retrieves a project by its key.

        Args:
            project_key: The key of the project.

        Returns:
            A promise that resolves to the project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__projects.get(f"/{project_key}", model=ProjectRead)

    @ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_key(self, project_key: str) -> ProjectRead:
        """
        Retrieves a project by its key.
        Alias for the get method.

        Args:
            project_key: The key of the project.

        Returns:
            A promise that resolves to the project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(project_key)

    @ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_id(self, project_id: str) -> ProjectRead:
        """
        Retrieves a project by its ID.
        Alias for the get method.

        Args:
            project_id: The ID of the project.

        Returns:
            A promise that resolves to the project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(project_id)

    @ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    @validate_arguments
    async def create(self, project_data: ProjectCreate) -> ProjectRead:
        """
        Creates a new project.

        Args:
            project_data: The data for the new project.

        Returns:
            A promise that resolves to the created project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__projects.post("", model=ProjectRead, json=project_data)

    @ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    @validate_arguments
    async def update(
        self, project_key: str, project_data: ProjectUpdate
    ) -> ProjectRead:
        """
        Updates a project.

        Args:
            project_key: The key of the project.
            project_data: The updated data for the project.

        Returns:
            A promise that resolves to the updated project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__projects.patch(
            f"/{project_key}", model=ProjectRead, json=project_data
        )

    @ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    @validate_arguments
    async def delete(self, project_key: str) -> None:
        """
        Deletes a project.

        Args:
            project_key: The key of the project to delete.

        Returns:
            A promise that resolves when the project is deleted.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__projects.delete(f"/{project_key}")
