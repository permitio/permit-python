from typing import List

from pydantic import validate_arguments

from .base import BasePermitApi, SimpleHttpClient, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import PaginatedResultUserRead, TenantCreate, TenantRead, TenantUpdate


class TenantsApi(BasePermitApi):
    @property
    def __tenants(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/tenants".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.__tenants.get(
            "", model=List[TenantRead], params=pagination_params(page, per_page)
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def list_tenant_users(
        self, tenant_key: str, page: int = 1, per_page: int = 100
    ) -> PaginatedResultUserRead:
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
        return await self.__tenants.get(
            f"/{tenant_key}/users",
            model=PaginatedResultUserRead,
            params=pagination_params(page, per_page),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.__tenants.get(f"/{tenant_key}", model=TenantRead)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.get(tenant_key)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.get(tenant_id)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.__tenants.post("", model=TenantRead, json=tenant_data)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.__tenants.patch(
            f"/{tenant_key}", model=TenantRead, json=tenant_data
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.__tenants.delete(f"/{tenant_key}")

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
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
        return await self.__tenants.delete(f"/{tenant_key}/users/{user_key}")
