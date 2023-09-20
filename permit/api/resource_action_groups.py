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
from .models import (
    ResourceActionGroupCreate,
    ResourceActionGroupRead,
    ResourceActionGroupUpdate,
)


class ResourceActionGroupsApi(BasePermitApi):
    @property
    def __action_groups(self) -> SimpleHttpClient:
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

    async def _get(self, resource_key: str, group_key: str) -> ResourceActionGroupRead:
        return await self.__action_groups.get(
            f"/{resource_key}/action_groups/{group_key}",
            model=ResourceActionGroupRead,
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
        return await self._get(resource_key, group_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
        return await self._get(resource_key, group_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
        return await self._get(resource_id, group_id)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def update(
        self, resource_key: str, group_key: str, group_data: ResourceActionGroupUpdate
    ) -> ResourceActionGroupRead:
        """
        Updates an action group.

        Args:
            resource_key: The key of the resource the action group belongs to.
            group_key: The key of the action group.
            group_data: The updated data for the action group.

        Returns:
            the updated action group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__action_groups.patch(
            f"/{resource_key}/action_groups/{group_key}",
            model=ResourceActionGroupRead,
            json=group_data,
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
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
