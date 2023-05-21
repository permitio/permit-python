from typing import List

from pydantic import validate_arguments

from .base import BasePermitApi, SimpleHttpClient, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import ConditionSetCreate, ConditionSetRead, ConditionSetUpdate


class ConditionSetsApi(BasePermitApi):
    @property
    def __condition_sets(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/schema/{proj_id}/{env_id}/condition_sets".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> List[ConditionSetRead]:
        """
        Retrieves a list of condition sets.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of condition sets.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__condition_sets.get(
            "", model=List[ConditionSetRead], params=pagination_params(page, per_page)
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get(self, condition_set_key: str) -> ConditionSetRead:
        """
        Retrieves a condition set by its key.

        Args:
            condition_set_key: The key of the condition set.

        Returns:
            the condition set.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__condition_sets.get(
            f"/{condition_set_key}", model=ConditionSetRead
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_key(self, condition_set_key: str) -> ConditionSetRead:
        """
        Retrieves a condition set by its key.
        Alias for the get method.

        Args:
            condition_set_key: The key of the condition set.

        Returns:
            the condition set.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(condition_set_key)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_id(self, condition_set_id: str) -> ConditionSetRead:
        """
        Retrieves a condition set by its ID.
        Alias for the get method.

        Args:
            condition_set_id: The ID of the condition set.

        Returns:
            the condition set.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(condition_set_id)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def create(self, condition_set_data: ConditionSetCreate) -> ConditionSetRead:
        """
        Creates a new condition set.

        Args:
            condition_set_data: The data for the new condition set.

        Returns:
            the created condition set.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__condition_sets.post(
            "", model=ConditionSetRead, json=condition_set_data
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def update(
        self, condition_set_key: str, condition_set_data: ConditionSetUpdate
    ) -> ConditionSetRead:
        """
        Updates a condition set.

        Args:
            condition_set_key: The key of the condition set.
            condition_set_data: The updated data for the condition set.

        Returns:
            the updated condition set.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__condition_sets.patch(
            f"/{condition_set_key}",
            model=ConditionSetRead,
            json=condition_set_data,
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def delete(self, condition_set_key: str) -> None:
        """
        Deletes a condition set.

        Args:
            condition_set_key: The key of the condition set to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__condition_sets.delete(f"/{condition_set_key}")
