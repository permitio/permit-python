from typing import List

from pydantic import validate_arguments

from .base import BasePermitApi, SimpleHttpClient, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import ResourceActionGroupCreate, ResourceActionGroupRead


class ResourceActionGroupsApi(BasePermitApi):
    @property
    def __action_groups(self) -> SimpleHttpClient:
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
    ) -> List[ResourceActionGroupRead]:
        """
        Retrieves a list of action groups.

        Args:
            resource_key: The key of the resource to filter on.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of action groups.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__action_groups.get(
            f"/{resource_key}/action_groups",
            model=List[ResourceActionGroupRead],
            params=pagination_params(page, per_page),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get(self, resource_key: str, group_key: str) -> ResourceActionGroupRead:
        """
        Retrieves a action group by its key.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group.

        Returns:
            the action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__action_groups.get(
            f"/{resource_key}/action_groups/{group_key}",
            model=ResourceActionGroupRead,
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_key(
        self, resource_key: str, group_key: str
    ) -> ResourceActionGroupRead:
        """
        Retrieves a action group by its key.
        Alias for the get method.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group.

        Returns:
            the action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(resource_key, group_key)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def get_by_id(
        self, resource_id: str, group_id: str
    ) -> ResourceActionGroupRead:
        """
        Retrieves a action group by its ID.
        Alias for the get method.

        Args:
            resource_key: The ID of the resource the action group belongs to.
            group_id: The ID of the action group.

        Returns:
            the action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.get(resource_id, group_id)

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def create(
        self, resource_key: str, group_data: ResourceActionGroupCreate
    ) -> ResourceActionGroupRead:
        """
        Creates a new action group.

        Args:
            resource_key: The key of the resource under which the action group should be created.
            group_data: The data for the new action group.

        Returns:
            the created action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__action_groups.post(
            f"/{resource_key}/action_groups",
            model=ResourceActionGroupRead,
            json=group_data,
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    @validate_arguments
    async def delete(self, resource_key: str, group_key: str) -> None:
        """
        Deletes a action group.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__action_groups.delete(
            f"/{resource_key}/action_groups/{group_key}"
        )
