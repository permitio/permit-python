from typing import List

from pydantic import validate_arguments

from .base import BasePermitApi, SimpleHttpClient, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import ResourceCreate, ResourceRead, ResourceReplace, ResourceUpdate


class ResourcesApi(BasePermitApi):
    @property
    def __resources(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/schema/{proj_id}/{env_id}/resources".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> List[ResourceRead]:
        """
        Retrieves a list of resources.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of resources.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resources.get(
            "",
            model=List[ResourceRead],
            params=pagination_params(page, per_page),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get(self, resource_key: str) -> ResourceRead:
        """
        Retrieves a resource by its key.

        Args:
            resource_key: The key of the resource.

        Returns:
            the resource.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resources.get(f"/{resource_key}", model=ResourceRead)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_key(self, resource_key: str) -> ResourceRead:
        """
        Retrieves a resource by its key.
        Alias for the get method.

        Args:
            resource_key: The key of the resource.

        Returns:
            the resource.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(resource_key)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_id(self, resource_id: str) -> ResourceRead:
        """
        Retrieves a resource by its ID.
        Alias for the get method.

        Args:
            resource_id: The ID of the resource.

        Returns:
            the resource.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(resource_id)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def create(self, resource_data: ResourceCreate) -> ResourceRead:
        """
        Creates a new resource.

        Args:
            resource_data: The data for the new resource.

        Returns:
            the created resource.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resources.post("", model=ResourceRead, json=resource_data)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def update(
        self, resource_key: str, resource_data: ResourceUpdate
    ) -> ResourceRead:
        """
        Updates a resource.

        Args:
            resource_key: The key of the resource.
            resource_data: The updated data for the resource.

        Returns:
            the updated resource.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resources.patch(
            f"/{resource_key}",
            model=ResourceRead,
            json=resource_data,
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def replace(
        self, resource_key: str, resource_data: ResourceReplace
    ) -> ResourceRead:
        """
        Creates a resource if no such resource exists, otherwise completely replaces the resource in place.

        Args:
            resource_key: The key of the resource.
            resource_data: The updated data for the resource.

        Returns:
            the updated resource.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resources.put(
            f"/{resource_key}",
            model=ResourceRead,
            json=resource_data,
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def delete(self, resource_key: str) -> None:
        """
        Deletes a resource.

        Args:
            resource_key: The key of the resource to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resources.delete(f"/{resource_key}")
