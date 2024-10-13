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
from .models import ConditionSetCreate, ConditionSetRead, ConditionSetUpdate


class ConditionSetsApi(BasePermitApi):
    @property
    def __condition_sets(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/condition_sets"
        )

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__condition_sets.get(
            "", model=List[ConditionSetRead], params=pagination_params(page, per_page)
        )

    async def _get(self, condition_set_key: str) -> ConditionSetRead:
        return await self.__condition_sets.get(f"/{condition_set_key}", model=ConditionSetRead)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(condition_set_key)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(condition_set_key)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(condition_set_id)

    @validate_arguments  # type: ignore[operator]
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__condition_sets.post("", model=ConditionSetRead, json=condition_set_data)

    @validate_arguments  # type: ignore[operator]
    async def update(self, condition_set_key: str, condition_set_data: ConditionSetUpdate) -> ConditionSetRead:
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
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__condition_sets.patch(
            f"/{condition_set_key}",
            model=ConditionSetRead,
            json=condition_set_data,
        )

    @validate_arguments  # type: ignore[operator]
    async def delete(self, condition_set_key: str) -> None:
        """
        Deletes a condition set.

        Args:
            condition_set_key: The key of the condition set to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__condition_sets.delete(f"/{condition_set_key}")
