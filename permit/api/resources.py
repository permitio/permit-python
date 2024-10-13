from typing import List

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
from .models import ResourceCreate, ResourceRead, ResourceReplace, ResourceUpdate


class ResourcesApi(BasePermitApi):
    @property
    def __resources(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/resources"
        )

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resources.get(
            "",
            model=List[ResourceRead],
            params=pagination_params(page, per_page),
        )

    async def _get(self, resource_key: str) -> ResourceRead:
        return await self.__resources.get(f"/{resource_key}", model=ResourceRead)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_id)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resources.post("", model=ResourceRead, json=resource_data)

    @validate_arguments  # type: ignore[operator]
    async def update(self, resource_key: str, resource_data: ResourceUpdate) -> ResourceRead:
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resources.patch(
            f"/{resource_key}",
            model=ResourceRead,
            json=resource_data,
        )

    @validate_arguments  # type: ignore[operator]
    async def replace(self, resource_key: str, resource_data: ResourceReplace) -> ResourceRead:
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resources.put(
            f"/{resource_key}",
            model=ResourceRead,
            json=resource_data,
        )

    @validate_arguments  # type: ignore[operator]
    async def delete(self, resource_key: str) -> None:
        """
        Deletes a resource.

        Args:
            resource_key: The key of the resource to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resources.delete(f"/{resource_key}")
