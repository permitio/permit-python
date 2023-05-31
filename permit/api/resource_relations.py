from typing import List

from pydantic import validate_arguments

from .base import BasePermitApi, SimpleHttpClient, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import RelationCreate, RelationRead


class ResourceRelationsApi(BasePermitApi):
    @property
    def __relations(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/schema/{proj_id}/{env_id}/resources".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def list(
        self, resource_key: str, page: int = 1, per_page: int = 100
    ) -> List[RelationRead]:
        """
        Retrieves a list of outgoing relations originating in a specific (object) resource.

        Args:
            resource_key: The key of the resource to filter on.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of relations.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__relations.get(
            f"/{resource_key}/relations",
            model=List[RelationRead],
            params=pagination_params(page, per_page),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get(self, resource_key: str, relation_key: str) -> RelationRead:
        """
        Retrieves a relation by its key.

        Args:
            resource_key: The key of the resource the relation belongs to.
            relation_key: The key of the relation.

        Returns:
            the relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__relations.get(
            f"/{resource_key}/relations/{relation_key}", model=RelationRead
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_key(self, resource_key: str, relation_key: str) -> RelationRead:
        """
        Retrieves a relation by its key.
        Alias for the get method.

        Args:
            resource_key: The key of the resource the relation belongs to.
            relation_key: The key of the relation.

        Returns:
            the relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(resource_key, relation_key)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_id(self, resource_id: str, relation_id: str) -> RelationRead:
        """
        Retrieves a relation by its ID.
        Alias for the get method.

        Args:
            resource_key: The ID of the resource the relation belongs to.
            relation_id: The ID of the relation.

        Returns:
            the relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(resource_id, relation_id)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def create(
        self, resource_key: str, relation_data: RelationCreate
    ) -> RelationRead:
        """
        Creates a new relation.

        Args:
            resource_key: The key of the resource under which the relation should be created.
            relation_data: The data for the new relation.

        Returns:
            the created relation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__relations.post(
            f"/{resource_key}/relations",
            model=RelationRead,
            json=relation_data,
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def delete(self, resource_key: str, relation_key: str) -> None:
        """
        Deletes a relation.

        Args:
            resource_key: The key of the resource the relation belongs to.
            relation_key: The key of the relation to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__relations.delete(
            f"/{resource_key}/relations/{relation_key}"
        )
