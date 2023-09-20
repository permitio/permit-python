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

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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

    async def _get(self, resource_key: str, relation_key: str) -> RelationRead:
        return await self.__relations.get(
            f"/{resource_key}/relations/{relation_key}", model=RelationRead
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
        return await self._get(resource_key, relation_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
        return await self._get(resource_key, relation_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
        return await self._get(resource_id, relation_id)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
