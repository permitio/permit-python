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
from permit.api.models import (
    APIKeyRead,
    EnvironmentCopy,
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentStats,
    EnvironmentUpdate,
)
from permit.config import PermitConfig


class EnvironmentsApi(BasePermitApi):
    """Manage the environments of a project."""

    def __init__(self, config: PermitConfig) -> None:
        super().__init__(config)
        self.__environments = self._build_http_client("")

    @validate_arguments
    async def list(
        self, project_key: str, page: int = 1, per_page: int = 100
    ) -> list[EnvironmentRead]:
        """Retrieves a list of environments.

        Args:
            project_key: The key of the project whose environments to list.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of EnvironmentRead objects representing the listed environments.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__environments.get(
            f"/v2/projects/{project_key}/envs",
            model=list[EnvironmentRead],
            params=pagination_params(page, per_page),
        )

    async def _get(self, project_key: str, environment_key: str) -> EnvironmentRead:
        return await self.__environments.get(
            f"/v2/projects/{project_key}/envs/{environment_key}", model=EnvironmentRead
        )

    @validate_arguments
    async def get(self, project_key: str, environment_key: str) -> EnvironmentRead:
        """Gets an environment by project key and environment key.

        Args:
            project_key: The project key.
            environment_key: The environment key.

        Returns:
            an EnvironmentRead object representing the retrieved environment.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self._get(project_key, environment_key)

    @validate_arguments
    async def get_by_key(self, project_key: str, environment_key: str) -> EnvironmentRead:
        """Gets an environment by project key and environment key.

        Alias for the get method.

        Args:
            project_key: The project key.
            environment_key: The environment key.

        Returns:
            an EnvironmentRead object representing the retrieved environment.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self._get(project_key, environment_key)

    @validate_arguments
    async def get_by_id(self, project_id: str, environment_id: str) -> EnvironmentRead:
        """Gets an environment by project ID and environment ID.

        Alias for the get method.

        Args:
            project_id: The project ID.
            environment_id: The environment ID.

        Returns:
            an EnvironmentRead object representing the retrieved environment.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self._get(project_id, environment_id)

    @validate_arguments
    async def get_stats(self, project_key: str, environment_key: str) -> EnvironmentStats:
        """Retrieves statistics and metadata for an environment.

        Args:
            project_key: The project key.
            environment_key: The environment key.

        Returns:
            an EnvironmentStats object representing the statistics data.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__environments.get(
            f"/v2/projects/{project_key}/envs/{environment_key}/stats",
            model=EnvironmentStats,
        )

    @validate_arguments
    async def get_api_key(self, project_key: str, environment_key: str) -> APIKeyRead:
        """Retrieves the API key that grants access for an environment.

        Args:
            project_key: The project key.
            environment_key: The environment key.

        Returns:
            an APIKeyRead object containing the API key and its metadata.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__environments.get(
            f"/v2/api-key/{project_key}/{environment_key}",
            model=APIKeyRead,
        )

    @validate_arguments
    async def create(
        self, project_key: str, environment_data: EnvironmentCreate
    ) -> EnvironmentRead:
        """Creates a new environment.

        Args:
            project_key: The project key.
            environment_data: The data for creating the environment.

        Returns:
            an EnvironmentRead object representing the created environment.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__environments.post(
            f"/v2/projects/{project_key}/envs",
            model=EnvironmentRead,
            json=environment_data,
        )

    @validate_arguments
    async def update(
        self,
        project_key: str,
        environment_key: str,
        environment_data: EnvironmentUpdate,
    ) -> EnvironmentRead:
        """Updates an existing environment.

        Args:
            project_key: The project key.
            environment_key: The environment key.
            environment_data: The data for updating the environment.

        Returns:
            an EnvironmentRead object representing the updated environment.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__environments.patch(
            f"/v2/projects/{project_key}/envs/{environment_key}",
            model=EnvironmentRead,
            json=environment_data,
        )

    @validate_arguments
    async def copy(
        self, project_key: str, environment_key: str, copy_params: EnvironmentCopy
    ) -> EnvironmentRead:
        """Clones data from a source environment into another environment of the same project.

        Args:
            project_key: The project key.
            environment_key: The environment key.
            copy_params: The parameters for copying the environment.

        Returns:
            an EnvironmentRead object representing the copied environment.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__environments.post(
            f"/v2/projects/{project_key}/envs/{environment_key}/copy",
            model=EnvironmentRead,
            json=copy_params,
        )

    @validate_arguments
    async def delete(self, project_key: str, environment_key: str) -> None:
        """Deletes an environment.

        Args:
            project_key: The project key.
            environment_key: The environment key.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ORGANIZATION)
        return await self.__environments.delete(
            f"/v2/projects/{project_key}/envs/{environment_key}"
        )
