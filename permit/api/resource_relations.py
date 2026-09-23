from typing import TYPE_CHECKING

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from permit.api.base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
)
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import PaginatedResultRelationRead, RelationCreate, RelationRead


class ResourceRelationsApi(BasePermitApi):
    """Manage the relations between resources (ReBAC)."""

    @property
    def __relations(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/resources"
        )

    @validate_arguments
    async def list(
        self, resource_key: str, page: int = 1, per_page: int = 100
    ) -> PaginatedResultRelationRead:
        """Retrieves a list of outgoing relations originating in a specific (object) resource.

        Args:
            resource_key: The key of the resource to filter on.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            a PaginatedResultRelationRead holding the relations in ``.data`` and the
            total number of relations on the resource in ``.total_count``.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__relations.get(
            f"/{resource_key}/relations",
            model=PaginatedResultRelationRead,
            params=pagination_params(page, per_page),
        )

    async def _get(self, resource_key: str, relation_key: str) -> RelationRead:
        return await self.__relations.get(
            f"/{resource_key}/relations/{relation_key}", model=RelationRead
        )

    @validate_arguments
    async def get(self, resource_key: str, relation_key: str) -> RelationRead:
        """Retrieves a relation by its key.

        Args:
            resource_key: The key of the resource the relation belongs to.
            relation_key: The key of the relation.

        Returns:
            the relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, relation_key)

    @validate_arguments
    async def get_by_key(self, resource_key: str, relation_key: str) -> RelationRead:
        """Retrieves a relation by its key.

        Alias for the get method.

        Args:
            resource_key: The key of the resource the relation belongs to.
            relation_key: The key of the relation.

        Returns:
            the relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, relation_key)

    @validate_arguments
    async def get_by_id(self, resource_id: str, relation_id: str) -> RelationRead:
        """Retrieves a relation by its ID.

        Alias for the get method.

        Args:
            resource_id: The ID of the resource the relation belongs to.
            relation_id: The ID of the relation.

        Returns:
            the relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_id, relation_id)

    @validate_arguments
    async def create(self, resource_key: str, relation_data: RelationCreate) -> RelationRead:
        """Creates a new relation.

        Args:
            resource_key: The key of the resource under which the relation should be created.
            relation_data: The data for the new relation.

        Returns:
            the created relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__relations.post(
            f"/{resource_key}/relations",
            model=RelationRead,
            json=relation_data,
        )

    @validate_arguments
    async def delete(self, resource_key: str, relation_key: str) -> None:
        """Deletes a relation.

        Args:
            resource_key: The key of the resource the relation belongs to.
            relation_key: The key of the relation to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__relations.delete(f"/{resource_key}/relations/{relation_key}")
