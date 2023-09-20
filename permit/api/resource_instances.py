from typing import List

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments  # type: ignore

from .base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
    required_context,
    required_permissions,
)
from .context import ApiContextLevel, ApiKeyAccessLevel
from .models import ResourceInstanceCreate, ResourceInstanceRead, ResourceInstanceUpdate


class ResourceInstancesApi(BasePermitApi):
    @property
    def __resource_instances(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/resource_instances".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def list(
        self, page: int = 1, per_page: int = 100
    ) -> List[ResourceInstanceRead]:
        """
        Retrieves a list of resource instances.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of resource instances.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_instances.get(
            "",
            model=List[ResourceInstanceRead],
            params=pagination_params(page, per_page),
        )

    async def _get(self, instance_key: str) -> ResourceInstanceRead:
        return await self.__resource_instances.get(
            f"/{instance_key}", model=ResourceInstanceRead
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def get(self, instance_key: str) -> ResourceInstanceRead:
        """
        Retrieves a resource instance by its key.

        Args:
            instance_key: The key of the resource instance.

        Returns:
            the resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self._get(instance_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def get_by_key(self, instance_key: str) -> ResourceInstanceRead:
        """
        Retrieves a resource instance by its key.
        Alias for the get method.

        Args:
            instance_key: The key of the resource instance.

        Returns:
            the resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self._get(instance_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def get_by_id(self, instance_id: str) -> ResourceInstanceRead:
        """
        Retrieves a resource instance by its ID.
        Alias for the get method.

        Args:
            instance_id: The ID of the resource instance.

        Returns:
            the resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self._get(instance_id)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def create(
        self, instance_data: ResourceInstanceCreate
    ) -> ResourceInstanceRead:
        """
        Creates a new resource instance.

        Args:
            instance_data: The data for the new resource instance.

        Returns:
            the created resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_instances.post(
            "", model=ResourceInstanceRead, json=instance_data
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def update(
        self, instance_key: str, instance_data: ResourceInstanceUpdate
    ) -> ResourceInstanceRead:
        """
        Updates a resource instance.

        Args:
            instance_key: The key of the resource instance.
            instance_data: The updated data for the resource instance.

        Returns:
            the updated resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_instances.patch(
            f"/{instance_key}",
            model=ResourceInstanceRead,
            json=instance_data,
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def delete(self, instance_key: str) -> None:
        """
        Deletes a resource instance.

        Args:
            instance_key: The key of the resource instance to delete.

        Returns:
            A promise that resolves when the resource instance is deleted.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_instances.delete(f"/{instance_key}")
