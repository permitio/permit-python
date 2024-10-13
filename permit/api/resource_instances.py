from typing import List, Optional

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
    ResourceInstanceCreate,
    ResourceInstanceCreateBulkOperation,
    ResourceInstanceCreateBulkOperationResult,
    ResourceInstanceDeleteBulkOperation,
    ResourceInstanceDeleteBulkOperationResult,
    ResourceInstanceRead,
    ResourceInstanceUpdate,
)


class ResourceInstancesApi(BasePermitApi):
    @property
    def __resource_instances(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/resource_instances", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/resource_instances"
            )

    @property
    def __bulk_operations(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/bulk/resource_instances", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/bulk/resource_instances"
            )

    @validate_arguments  # type: ignore[operator]
    async def list(
        self,
        page: int = 1,
        per_page: int = 100,
        tenant_key: Optional[str] = None,
        resource_key: Optional[str] = None,
        detailed_key: Optional[bool] = None,
        search_key: Optional[str] = None,
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = pagination_params(page, per_page)
        if tenant_key is not None:
            params.update(tenant=tenant_key)
        if resource_key is not None:
            params.update(resource=resource_key)
        if detailed_key is not None:
            params.update(detailed=detailed_key)
        if search_key is not None:
            params.update(search=search_key)

        return await self.__resource_instances.get(
            "",
            model=List[ResourceInstanceRead],
            params=params,
        )

    async def _get(self, instance_key: str) -> ResourceInstanceRead:
        return await self.__resource_instances.get(f"/{instance_key}", model=ResourceInstanceRead)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(instance_key)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(instance_key)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(instance_id)

    @validate_arguments  # type: ignore[operator]
    async def create(self, instance_data: ResourceInstanceCreate) -> ResourceInstanceRead:
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resource_instances.post("", model=ResourceInstanceRead, json=instance_data)

    @validate_arguments  # type: ignore[operator]
    async def update(self, instance_key: str, instance_data: ResourceInstanceUpdate) -> ResourceInstanceRead:
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resource_instances.patch(
            f"/{instance_key}",
            model=ResourceInstanceRead,
            json=instance_data,
        )

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resource_instances.delete(f"/{instance_key}")

    @validate_arguments  # type: ignore[operator]
    async def bulk_replace(
        self, resource_instances: List[ResourceInstanceCreate]
    ) -> ResourceInstanceCreateBulkOperationResult:
        """
        Creates (and if need replaces) resource instances in bulk.

        If the resource instance exists - replaces it.
        Otherwise creates previously non-existing resource instances.

        Args:
            resource_instances: The resource instances to create/replace.

        Returns:
            the bulk replace report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.put(
            "",
            model=ResourceInstanceCreateBulkOperationResult,
            json=ResourceInstanceCreateBulkOperation(operations=resource_instances),
        )

    @validate_arguments  # type: ignore[operator]
    async def bulk_delete(self, resource_instances: List[str]) -> ResourceInstanceDeleteBulkOperationResult:
        """
        Deletes resource instances in bulk.

        Args:
            resource_instances: The resource instance identities to delete.
            Each identity can be either `resource_type:instance_key` (like Repository:react) or the resource instance uuid.

        Returns:
            the bulk delete report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """  # noqa: E501
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.delete(
            "",
            model=ResourceInstanceDeleteBulkOperationResult,
            json=ResourceInstanceDeleteBulkOperation(idents=resource_instances),
        )
