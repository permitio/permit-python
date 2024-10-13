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
from .models import ResourceActionCreate, ResourceActionRead, ResourceActionUpdate


class ResourceActionsApi(BasePermitApi):
    @property
    def __actions(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/resources"
        )

    @validate_arguments  # type: ignore[operator]
    async def list(self, resource_key: str, page: int = 1, per_page: int = 100) -> List[ResourceActionRead]:
        """
        Retrieves a list of actions.

        Args:
            resource_key: The key of the resource to filter on.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of actions.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__actions.get(
            f"/{resource_key}/actions",
            model=List[ResourceActionRead],
            params=pagination_params(page, per_page),
        )

    async def _get(self, resource_key: str, action_key: str) -> ResourceActionRead:
        return await self.__actions.get(f"/{resource_key}/actions/{action_key}", model=ResourceActionRead)

    @validate_arguments  # type: ignore[operator]
    async def get(self, resource_key: str, action_key: str) -> ResourceActionRead:
        """
        Retrieves a action by its key.

        Args:
            resource_key: The key of the resource the action belongs to.
            action_key: The key of the action.

        Returns:
            the action.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, action_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_key(self, resource_key: str, action_key: str) -> ResourceActionRead:
        """
        Retrieves a action by its key.
        Alias for the get method.

        Args:
            resource_key: The key of the resource the action belongs to.
            action_key: The key of the action.

        Returns:
            the action.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, action_key)

    @validate_arguments  # type: ignore[operator]
    async def get_by_id(self, resource_id: str, action_id: str) -> ResourceActionRead:
        """
        Retrieves a action by its ID.
        Alias for the get method.

        Args:
            resource_key: The ID of the resource the action belongs to.
            action_id: The ID of the action.

        Returns:
            the action.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_id, action_id)

    @validate_arguments  # type: ignore[operator]
    async def create(self, resource_key: str, action_data: ResourceActionCreate) -> ResourceActionRead:
        """
        Creates a new action.

        Args:
            resource_key: The key of the resource under which the action should be created.
            action_data: The data for the new action.

        Returns:
            the created action.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__actions.post(
            f"/{resource_key}/actions",
            model=ResourceActionRead,
            json=action_data,
        )

    @validate_arguments  # type: ignore[operator]
    async def update(self, resource_key: str, action_key: str, action_data: ResourceActionUpdate) -> ResourceActionRead:
        """
        Updates a action.

        Args:
            resource_key: The key of the resource the action belongs to.
            action_key: The key of the action.
            action_data: The updated data for the action.

        Returns:
            the updated action.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__actions.patch(
            f"/{resource_key}/actions/{action_key}",
            model=ResourceActionRead,
            json=action_data,
        )

    @validate_arguments  # type: ignore[operator]
    async def delete(self, resource_key: str, action_key: str) -> None:
        """
        Deletes a action.

        Args:
            resource_key: The key of the resource the action belongs to.
            action_key: The key of the action to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__actions.delete(f"/{resource_key}/actions/{action_key}")
