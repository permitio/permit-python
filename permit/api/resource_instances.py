from typing import TYPE_CHECKING

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

import builtins

from permit.api.base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
)
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import (
    ResourceInstanceCreate,
    ResourceInstanceCreateBulkOperation,
    ResourceInstanceCreateBulkOperationResult,
    ResourceInstanceDeleteBulkOperation,
    ResourceInstanceDeleteBulkOperationResult,
    ResourceInstanceRead,
    ResourceInstanceUpdate,
)


class ResourceInstancesApi(BasePermitApi):
    """Manage resource instances."""

    @property
    def __resource_instances(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/resource_instances", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/resource_instances"
        )

    @property
    def __bulk_operations(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/bulk/resource_instances", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/bulk/resource_instances"
        )

    @validate_arguments
    async def list(  # noqa: PLR0917 - public signature; callers may pass these positionally
        self,
        page: int = 1,
        per_page: int = 100,
        tenant_key: str | None = None,
        resource_key: str | None = None,
        detailed_key: bool | None = None,  # noqa: FBT001 - public signature, positional callers
        search_key: str | None = None,
    ) -> list[ResourceInstanceRead]:
        """Retrieves a list of resource instances.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).
            tenant_key: Only return instances that belong to this tenant.
            resource_key: Only return instances of this resource type.
            detailed_key: Whether to return detailed instances.
            search_key: Only return instances matching this search string.

        Returns:
            an array of resource instances.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = pagination_params(page, per_page)
        if tenant_key is not None:
            params.update(tenant=tenant_key)
        if resource_key is not None:
            params.update(resource=resource_key)
        if detailed_key is not None:
            # yarl rejects bool query values, and the API parses these as booleans
            params.update(detailed="true" if detailed_key else "false")
        if search_key is not None:
            params.update(search=search_key)

        return await self.__resource_instances.get(
            "",
            model=list[ResourceInstanceRead],
            params=params,
        )

    async def _get(self, instance_key: str) -> ResourceInstanceRead:
        return await self.__resource_instances.get(f"/{instance_key}", model=ResourceInstanceRead)

    @validate_arguments
    async def get(self, instance_key: str) -> ResourceInstanceRead:
        """Retrieves a resource instance by its identity.

        Args:
            instance_key: The resource instance identity. Either `resource_type:instance_key`
                (like Repository:react) or the resource instance uuid. A bare instance key
                is rejected by the API with a 422.

        Returns:
            the resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(instance_key)

    @validate_arguments
    async def get_by_key(self, instance_key: str) -> ResourceInstanceRead:
        """Retrieves a resource instance by its identity.

        Alias for the get method.

        Args:
            instance_key: The resource instance identity. Either `resource_type:instance_key`
                (like Repository:react) or the resource instance uuid. A bare instance key
                is rejected by the API with a 422.

        Returns:
            the resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(instance_key)

    @validate_arguments
    async def get_by_id(self, instance_id: str) -> ResourceInstanceRead:
        """Retrieves a resource instance by its ID.

        Alias for the get method.

        Args:
            instance_id: The ID of the resource instance.

        Returns:
            the resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(instance_id)

    @validate_arguments
    async def create(self, instance_data: ResourceInstanceCreate) -> ResourceInstanceRead:
        """Creates a new resource instance.

        Args:
            instance_data: The data for the new resource instance.

        Returns:
            the created resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resource_instances.post(
            "", model=ResourceInstanceRead, json=instance_data
        )

    @validate_arguments
    async def update(
        self, instance_key: str, instance_data: ResourceInstanceUpdate
    ) -> ResourceInstanceRead:
        """Updates a resource instance.

        Args:
            instance_key: The resource instance identity. Either `resource_type:instance_key`
                (like Repository:react) or the resource instance uuid. A bare instance key
                is rejected by the API with a 422.
            instance_data: The updated data for the resource instance.

        Returns:
            the updated resource instance.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resource_instances.patch(
            f"/{instance_key}",
            model=ResourceInstanceRead,
            json=instance_data,
        )

    @validate_arguments
    async def delete(self, instance_key: str) -> None:
        """Deletes a resource instance.

        Args:
            instance_key: The identity of the resource instance to delete. Either
                `resource_type:instance_key`
                (like Repository:react) or the resource instance uuid. A bare instance key
                is rejected by the API with a 422.

        Returns:
            A promise that resolves when the resource instance is deleted.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__resource_instances.delete(f"/{instance_key}")

    @validate_arguments
    async def bulk_replace(
        self, resource_instances: builtins.list[ResourceInstanceCreate]
    ) -> ResourceInstanceCreateBulkOperationResult:
        """Creates (and if need replaces) resource instances in bulk.

        If the resource instance exists - replaces it.
        Otherwise creates previously non-existing resource instances.

        Args:
            resource_instances: The resource instances to create/replace.

        Returns:
            the bulk replace report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.put(
            "",
            model=ResourceInstanceCreateBulkOperationResult,
            json=ResourceInstanceCreateBulkOperation(operations=resource_instances),
        )

    @validate_arguments
    async def bulk_delete(
        self, resource_instances: builtins.list[str]
    ) -> ResourceInstanceDeleteBulkOperationResult:
        """Deletes resource instances in bulk.

        Args:
            resource_instances: The resource instance identities to delete.
            Each identity can be either `resource_type:instance_key` (like Repository:react) or the
            resource instance uuid.

        Returns:
            the bulk delete report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.delete(
            "",
            model=ResourceInstanceDeleteBulkOperationResult,
            json=ResourceInstanceDeleteBulkOperation(idents=resource_instances),
        )
