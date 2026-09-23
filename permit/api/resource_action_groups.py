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
from permit.api.models import (
    ResourceActionGroupCreate,
    ResourceActionGroupRead,
    ResourceActionGroupUpdate,
)


class ResourceActionGroupsApi(BasePermitApi):
    """Manage the action groups of a resource."""

    @property
    def __action_groups(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/resources"
        )

    @validate_arguments
    async def list(
        self, resource_key: str, page: int = 1, per_page: int = 100
    ) -> list[ResourceActionGroupRead]:
        """Retrieves a list of action groups.

        Args:
            resource_key: The key of the resource to filter on.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of action groups.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__action_groups.get(
            f"/{resource_key}/action_groups",
            model=list[ResourceActionGroupRead],
            params=pagination_params(page, per_page),
        )

    async def _get(self, resource_key: str, group_key: str) -> ResourceActionGroupRead:
        return await self.__action_groups.get(
            f"/{resource_key}/action_groups/{group_key}",
            model=ResourceActionGroupRead,
        )

    @validate_arguments
    async def get(self, resource_key: str, group_key: str) -> ResourceActionGroupRead:
        """Retrieves a action group by its key.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group.

        Returns:
            the action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, group_key)

    @validate_arguments
    async def get_by_key(self, resource_key: str, group_key: str) -> ResourceActionGroupRead:
        """Retrieves a action group by its key.

        Alias for the get method.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group.

        Returns:
            the action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_key, group_key)

    @validate_arguments
    async def get_by_id(self, resource_id: str, group_id: str) -> ResourceActionGroupRead:
        """Retrieves a action group by its ID.

        Alias for the get method.

        Args:
            resource_id: The ID of the resource the action group belongs to.
            group_id: The ID of the action group.

        Returns:
            the action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(resource_id, group_id)

    @validate_arguments
    async def create(
        self, resource_key: str, group_data: ResourceActionGroupCreate
    ) -> ResourceActionGroupRead:
        """Creates a new action group.

        Args:
            resource_key: The key of the resource under which the action group should be created.
            group_data: The data for the new action group.

        Returns:
            the created action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__action_groups.post(
            f"/{resource_key}/action_groups",
            model=ResourceActionGroupRead,
            json=group_data,
        )

    @validate_arguments
    async def update(
        self, resource_key: str, group_key: str, group_data: ResourceActionGroupUpdate
    ) -> ResourceActionGroupRead:
        """Updates an action group.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group.
            group_data: The updated data for the action group.

        Returns:
            the updated action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__action_groups.patch(
            f"/{resource_key}/action_groups/{group_key}",
            model=ResourceActionGroupRead,
            json=group_data,
        )

    @validate_arguments
    async def delete(self, resource_key: str, group_key: str) -> None:
        """Deletes a action group.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__action_groups.delete(f"/{resource_key}/action_groups/{group_key}")
