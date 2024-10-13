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
    PaginatedResultUserRead,
    TenantCreate,
    TenantCreateBulkOperation,
    TenantCreateBulkOperationResult,
    TenantDeleteBulkOperation,
    TenantDeleteBulkOperationResult,
    TenantRead,
    TenantUpdate,
)


class TenantsApi(BasePermitApi):
    @property
    def __tenants(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/tenants", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/tenants"
            )

    @property
    def __bulk_operations(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/users", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/bulk/tenants"
            )

    @validate_arguments  # type: ignore[operator]
    async def list(self, page: int = 1, per_page: int = 100) -> List[TenantRead]:
        """
        Retrieves a list of tenants.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of tenants.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.get("", model=List[TenantRead], params=pagination_params(page, per_page))

    @validate_arguments  # type: ignore[operator]
    async def list_tenant_users(self, tenant_key: str, page: int = 1, per_page: int = 100) -> PaginatedResultUserRead:
        """
        Retrieves a list of users for a given tenant.

        Args:
            tenant_key: The key of the tenant.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            a PaginatedResultUserRead object containing the list of tenant users.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.get(
            f"/{tenant_key}/users",
            model=PaginatedResultUserRead,
            params=pagination_params(page, per_page),
        )

    async def _get(self, tenant_key: str) -> TenantRead:
        return await self.__tenants.get(f"/{tenant_key}", model=TenantRead)

    @validate_arguments  # type: ignore[operator]
    async def get(self, tenant_key: str) -> TenantRead:
        """
        Retrieves a tenant by its key.

        Args:
            tenant_key: The key of the tenant.

        Returns:
            the tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(tenant_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_key(self, tenant_key: str) -> TenantRead:
        """
        Retrieves a tenant by its key.
        Alias for the get method.

        Args:
            tenant_key: The key of the tenant.

        Returns:
            the tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(tenant_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_id(self, tenant_id: str) -> TenantRead:
        """
        Retrieves a tenant by its ID.
        Alias for the get method.

        Args:
            tenant_id: The ID of the tenant.

        Returns:
            the tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(tenant_id)

    @validate_arguments  # type: ignore[operator]
    async def create(self, tenant_data: TenantCreate) -> TenantRead:
        """
        Creates a new tenant.

        Args:
            tenant_data: The data for the new tenant.

        Returns:
            the created tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.post("", model=TenantRead, json=tenant_data)

    @validate_arguments  # type: ignore[operator]
    async def update(self, tenant_key: str, tenant_data: TenantUpdate) -> TenantRead:
        """
        Updates a tenant.

        Args:
            tenant_key: The key of the tenant.
            tenant_data: The updated data for the tenant.

        Returns:
            the updated tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.patch(f"/{tenant_key}", model=TenantRead, json=tenant_data)

    @validate_arguments  # type: ignore[operator]
    async def delete(self, tenant_key: str) -> None:
        """
        Deletes a tenant.

        Args:
            tenant_key: The key of the tenant to delete.

        Returns:
            A promise that resolves when the tenant is deleted.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.delete(f"/{tenant_key}")

    @validate_arguments  # type: ignore[operator]
    async def delete_tenant_user(self, tenant_key: str, user_key: str) -> None:
        """
        Deletes a user from a given tenant (also removes all roles granted to the user in that tenant).

        Args:
            tenant_key: The key of the tenant from which the user will be deleted.
            user_key: The key of the user to be deleted.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.delete(f"/{tenant_key}/users/{user_key}")

    @validate_arguments  # type: ignore[operator]
    async def bulk_create(self, tenants: List[TenantCreate]) -> TenantCreateBulkOperationResult:
        """
        Creates tenants in bulk.

        Args:
            tenants: The tenants to create

        Returns:
            the bulk creation report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.post(
            "",
            model=TenantCreateBulkOperationResult,
            json=TenantCreateBulkOperation(operations=tenants),
        )

    @validate_arguments  # type: ignore[operator]
    async def bulk_delete(self, tenants: List[str]) -> TenantDeleteBulkOperationResult:
        """
        Deletes tenants in bulk.

        If the tenant exists - replaces it. Otherwise creates a non-existing tenant.

        Args:
            tenants: The tenants identities to delete. Each identity can be either the tenant key or the tenant id.

        Returns:
            the bulk delete report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.delete(
            "",
            model=TenantDeleteBulkOperationResult,
            json=TenantDeleteBulkOperation(idents=tenants),
        )
