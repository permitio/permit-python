from typing import List

from ..config import PermitConfig
from .base import BasePermitApi, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import (
    ResourceAttributeCreate,
    ResourceAttributeRead,
    ResourceAttributeUpdate,
)


class ResourceAttributesApi(BasePermitApi):
    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__attributes = self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/resources".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def list(
        self, resource_key: str, page: int = 1, per_page: int = 100
    ) -> List[ResourceAttributeRead]:
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
        return await self.__attributes.get(
            f"/{resource_key}/attributes",
            model=List[ResourceAttributeRead],
            params=pagination_params(page, per_page),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
        return await self.__attributes.get(
            f"/{resource_key}/attributes/{attribute_key}", model=ResourceAttributeRead
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def get_by_key(
        self, resource_key: str, attribute_key: str
    ) -> ResourceAttributeRead:
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
        return await self.get(resource_key, attribute_key)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def get_by_id(
        self, resource_id: str, attribute_id: str
    ) -> ResourceAttributeRead:
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
        return await self.get(resource_id, attribute_id)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def create(
        self, resource_key: str, attribute_data: ResourceAttributeCreate
    ) -> ResourceAttributeRead:
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
        return await self.__attributes.post(
            f"/{resource_key}/attributes",
            model=ResourceAttributeRead,
            json=attribute_data.dict(),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
        return await self.__attributes.patch(
            f"/{resource_key}/attributes/{attribute_key}",
            model=ResourceAttributeRead,
            json=attribute_data.dict(),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
        return await self.__attributes.delete(
            f"/{resource_key}/attributes/{attribute_key}"
        )
