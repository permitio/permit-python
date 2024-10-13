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
from .models import (
    ResourceAttributeCreate,
    ResourceAttributeRead,
    ResourceAttributeUpdate,
)


class ResourceAttributesApi(BasePermitApi):
    @property
    def __attributes(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/resources"
        )

    @validate_arguments  # type: ignore[operator]
    async def list(self, resource_key: str, page: int = 1, per_page: int = 100) -> List[ResourceAttributeRead]:
        """
        Retrieves a list of attributes.

        Args:
            resource_key: The key of the resource to filter on.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of attributes.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__attributes.get(
            f"/{resource_key}/attributes",
            model=List[ResourceAttributeRead],
            params=pagination_params(page, per_page),
        )

    async def _get(self, resource_key: str, attribute_key: str) -> ResourceAttributeRead:
        return await self.__attributes.get(f"/{resource_key}/attributes/{attribute_key}", model=ResourceAttributeRead)

    @validate_arguments  # type: ignore[operator]
    async def get(self, resource_key: str, attribute_key: str) -> ResourceAttributeRead:
        """
        Retrieves a attribute by its key.

        Args:
            resource_key: The key of the resource the attribute belongs to.
            attribute_key: The key of the attribute.

        Returns:
            the attribute.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, attribute_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_key(self, resource_key: str, attribute_key: str) -> ResourceAttributeRead:
        """
        Retrieves a attribute by its key.
        Alias for the get method.

        Args:
            resource_key: The key of the resource the attribute belongs to.
            attribute_key: The key of the attribute.

        Returns:
            the attribute.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, attribute_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_id(self, resource_id: str, attribute_id: str) -> ResourceAttributeRead:
        """
        Retrieves a attribute by its ID.
        Alias for the get method.

        Args:
            resource_key: The ID of the resource the attribute belongs to.
            attribute_id: The ID of the attribute.

        Returns:
            the attribute.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_id, attribute_id)

    @validate_arguments  # type: ignore[operator]
    async def create(self, resource_key: str, attribute_data: ResourceAttributeCreate) -> ResourceAttributeRead:
        """
        Creates a new attribute.

        Args:
            resource_key: The key of the resource under which the attribute should be created.
            attribute_data: The data for the new attribute.

        Returns:
            the created attribute.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__attributes.post(
            f"/{resource_key}/attributes",
            model=ResourceAttributeRead,
            json=attribute_data,
        )

    @validate_arguments  # type: ignore[operator]
    async def update(
        self,
        resource_key: str,
        attribute_key: str,
        attribute_data: ResourceAttributeUpdate,
    ) -> ResourceAttributeRead:
        """
        Updates a attribute.

        Args:
            resource_key: The key of the resource the attribute belongs to.
            attribute_key: The key of the attribute.
            attribute_data: The updated data for the attribute.

        Returns:
            the updated attribute.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__attributes.patch(
            f"/{resource_key}/attributes/{attribute_key}",
            model=ResourceAttributeRead,
            json=attribute_data,
        )

    @validate_arguments  # type: ignore[operator]
    async def delete(self, resource_key: str, attribute_key: str) -> None:
        """
        Deletes a attribute.

        Args:
            resource_key: The key of the resource the attribute belongs to.
            attribute_key: The key of the attribute to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__attributes.delete(f"/{resource_key}/attributes/{attribute_key}")
