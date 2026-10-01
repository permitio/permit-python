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

from permit.api.base import BasePermitApi, SimpleHttpClient, pagination_params
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import (
    PaginatedResultUserRead,
    TenantCreate,
    TenantCreateBulkOperation,
    TenantCreateBulkOperationResult,
    TenantDeleteBulkOperation,
    TenantDeleteBulkOperationResult,
    TenantRead,
    TenantUpdate,
    UserCreate,
    UserRead,
)
from permit.utils.model_input import ModelInput, ModelListInput


class TenantsApi(BasePermitApi):
    """Manage tenants and the users in them."""

    @property
    def __tenants(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/tenants", use_pdp=True)
        return self.__api_tenants

    @property
    def __api_tenants(self) -> SimpleHttpClient:
        """The tenants collection on the Permit REST API, whatever proxy_facts_via_pdp says."""
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/tenants"
        )

    @property
    def __bulk_operations(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/bulk/tenants", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/bulk/tenants"
        )

    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> list[TenantRead]:
        """Retrieves a list of tenants.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of tenants.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.get(
            "", model=list[TenantRead], params=pagination_params(page, per_page)
        )

    @validate_arguments
    async def list_tenant_users(
        self, tenant_key: str, page: int = 1, per_page: int = 100
    ) -> PaginatedResultUserRead:
        """Retrieves a list of users for a given tenant.

        Args:
            tenant_key: The key of the tenant.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            a PaginatedResultUserRead object containing the list of tenant users.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.get(
            f"/{tenant_key}/users",
            model=PaginatedResultUserRead,
            params=pagination_params(page, per_page),
        )

    @validate_arguments
    async def add_user(self, tenant_key: str, user_data: ModelInput[UserCreate]) -> UserRead:
        """Creates a user as a member of a tenant.

        The API creates the user and adds it to the tenant without any role. It answers 409
        when a user with that key already exists, whichever tenants it is in, so this cannot
        add an existing user to another tenant: grant that user a role in the tenant with
        ``api.users.assign_role()`` instead. Role assignments listed in ``user_data`` are
        granted as ``api.users.create()`` grants them, each in the tenant it names.

        The request always goes to the Permit REST API, even with ``proxy_facts_via_pdp``
        set, so ``wait_for_sync()`` does not make it wait for the PDP. A membership without a
        role does not show in ``permit.get_user_tenants()``, which lists the tenants in which
        the user has a role, and ``delete_tenant_user()`` cannot remove it: delete the user
        with ``api.users.delete()`` instead.

        Needs an environment-level API key, or a broader key with the SDK's API context set
        to the environment.

        Args:
            tenant_key: The key or id of the tenant.
            user_data: The user to create, as a ``UserCreate`` or an equivalent dict.

        Returns:
            the created user, whose ``associated_tenants`` include the tenant.

        Raises:
            PermitAlreadyExistsError: If a user with this key already exists.
            PermitNotFoundError: If the tenant does not exist.
            PermitApiError: If the API returns any other error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__api_tenants.post(f"/{tenant_key}/users", model=UserRead, json=user_data)

    async def _get(self, tenant_key: str) -> TenantRead:
        return await self.__tenants.get(f"/{tenant_key}", model=TenantRead)

    @validate_arguments
    async def get(self, tenant_key: str) -> TenantRead:
        """Retrieves a tenant by its key.

        Args:
            tenant_key: The key of the tenant.

        Returns:
            the tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(tenant_key)

    @validate_arguments
    async def get_by_key(self, tenant_key: str) -> TenantRead:
        """Retrieves a tenant by its key.

        Alias for the get method.

        Args:
            tenant_key: The key of the tenant.

        Returns:
            the tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(tenant_key)

    @validate_arguments
    async def get_by_id(self, tenant_id: str) -> TenantRead:
        """Retrieves a tenant by its ID.

        Alias for the get method.

        Args:
            tenant_id: The ID of the tenant.

        Returns:
            the tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(tenant_id)

    @validate_arguments
    async def create(self, tenant_data: ModelInput[TenantCreate]) -> TenantRead:
        """Creates a new tenant.

        Args:
            tenant_data: The data for the new tenant.

        Returns:
            the created tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.post("", model=TenantRead, json=tenant_data)

    @validate_arguments
    async def update(self, tenant_key: str, tenant_data: ModelInput[TenantUpdate]) -> TenantRead:
        """Updates a tenant.

        Args:
            tenant_key: The key of the tenant.
            tenant_data: The updated data for the tenant.

        Returns:
            the updated tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.patch(f"/{tenant_key}", model=TenantRead, json=tenant_data)

    @validate_arguments
    async def delete(self, tenant_key: str) -> None:
        """Deletes a tenant.

        Args:
            tenant_key: The key of the tenant to delete.

        Returns:
            A promise that resolves when the tenant is deleted.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.delete(f"/{tenant_key}")

    @validate_arguments
    async def delete_tenant_user(self, tenant_key: str, user_key: str) -> None:
        """Removes the roles a user holds in a tenant.

        The API removes the user's tenant-level roles in the tenant, and answers 404 when the
        user holds none there. That includes a member that ``add_user()`` created without a
        role, which this cannot remove: delete such a user with ``api.users.delete()``.

        When the user is then left with no tenant-level role in any tenant, the API deletes
        the user, even if the user is still a member of a tenant without a role or holds roles
        on resource instances, so ``add_user()`` can create a user with that key again.
        Otherwise the user stays a member of the tenant, with no tenant-level role there.

        Args:
            tenant_key: The key of the tenant.
            user_key: The key of the user whose roles in the tenant to remove.

        Raises:
            PermitApiError: If the user holds no tenant-level role in the tenant (404), or the
                API returns any other error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__tenants.delete(f"/{tenant_key}/users/{user_key}")

    @validate_arguments
    async def bulk_create(
        self, tenants: ModelListInput[TenantCreate]
    ) -> TenantCreateBulkOperationResult:
        """Creates tenants in bulk.

        Args:
            tenants: The tenants to create

        Returns:
            the bulk creation report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.post(
            "",
            model=TenantCreateBulkOperationResult,
            json=TenantCreateBulkOperation(operations=tenants),
        )

    @validate_arguments
    async def bulk_delete(self, tenants: builtins.list[str]) -> TenantDeleteBulkOperationResult:
        """Deletes tenants in bulk.

        Args:
            tenants: The tenants identities to delete. Each identity can be either the tenant key or
                the tenant id.

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
            model=TenantDeleteBulkOperationResult,
            json=TenantDeleteBulkOperation(idents=tenants),
        )
