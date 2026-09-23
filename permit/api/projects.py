from typing import TYPE_CHECKING

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from permit.api.base import (
    BasePermitApi,
    pagination_params,
)
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import ProjectCreate, ProjectRead, ProjectUpdate
from permit.config import PermitConfig


class ProjectsApi(BasePermitApi):
    """Manage the projects of an organization."""

    def __init__(self, config: PermitConfig) -> None:
        super().__init__(config)
        self.__projects = self._build_http_client("/v2/projects")

    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> list[ProjectRead]:
        """Retrieves a list of projects.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            A promise that resolves to an array of projects.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__projects.get(
            "", model=list[ProjectRead], params=pagination_params(page, per_page)
        )

    async def _get(self, project_key: str) -> ProjectRead:
        return await self.__projects.get(f"/{project_key}", model=ProjectRead)

    @validate_arguments
    async def get(self, project_key: str) -> ProjectRead:
        """Retrieves a project by its key.

        Args:
            project_key: The key of the project.

        Returns:
            A promise that resolves to the project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self._get(project_key)

    @validate_arguments
    async def get_by_key(self, project_key: str) -> ProjectRead:
        """Retrieves a project by its key.

        Alias for the get method.

        Args:
            project_key: The key of the project.

        Returns:
            A promise that resolves to the project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self._get(project_key)

    @validate_arguments
    async def get_by_id(self, project_id: str) -> ProjectRead:
        """Retrieves a project by its ID.

        Alias for the get method.

        Args:
            project_id: The ID of the project.

        Returns:
            A promise that resolves to the project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self._get(project_id)

    @validate_arguments
    async def create(self, project_data: ProjectCreate) -> ProjectRead:
        """Creates a new project.

        Args:
            project_data: The data for the new project.

        Returns:
            A promise that resolves to the created project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__projects.post("", model=ProjectRead, json=project_data)

    @validate_arguments
    async def update(self, project_key: str, project_data: ProjectUpdate) -> ProjectRead:
        """Updates a project.

        Args:
            project_key: The key of the project.
            project_data: The updated data for the project.

        Returns:
            A promise that resolves to the updated project.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__projects.patch(f"/{project_key}", model=ProjectRead, json=project_data)

    @validate_arguments
    async def delete(self, project_key: str) -> None:
        """Deletes a project.

        Args:
            project_key: The key of the project to delete.

        Returns:
            A promise that resolves when the project is deleted.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__projects.delete(f"/{project_key}")
