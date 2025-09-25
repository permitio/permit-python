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
from .models import (
    ElementsUserInviteApprove,
    ElementsUserInviteCreate,
    ElementsUserInviteRead,
    PaginatedResultElementsUserInviteRead,
    UserRead,
)


class UserInvitesApi(BasePermitApi):
    @property
    def __user_invites(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/user_invites"
        )

    @validate_arguments  # type: ignore[operator]
    async def list(self, page: int = 1, per_page: int = 100) -> PaginatedResultElementsUserInviteRead:
        """
        Retrieves a list of user invites.

        Args:
            page: The page number to retrieve (default: 1).
            per_page: The number of invites per page (default: 100).

        Returns:
            A paginated list of user invites.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__user_invites.get(
            "",
            model=PaginatedResultElementsUserInviteRead,
            params=pagination_params(page, per_page),
        )

    @validate_arguments  # type: ignore[operator]
    async def get(self, user_invite_id: str) -> ElementsUserInviteRead:
        """
        Retrieves a single user invite by ID.

        Args:
            user_invite_id: The ID of the user invite to retrieve.

        Returns:
            The user invite details.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__user_invites.get(f"/{user_invite_id}", model=ElementsUserInviteRead)

    @validate_arguments  # type: ignore[operator]
    async def create(self, user_invite_data: ElementsUserInviteCreate) -> ElementsUserInviteRead:
        """
        Creates a new user invite.

        Args:
            user_invite_data: The user invite data to create.

        Returns:
            The created user invite.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__user_invites.post("", model=ElementsUserInviteRead, json=user_invite_data)

    @validate_arguments  # type: ignore[operator]
    async def delete(self, user_invite_id: str) -> None:
        """
        Deletes a user invite.

        Args:
            user_invite_id: The ID of the user invite to delete.

        Returns:
            None

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        await self.__user_invites.delete(f"/{user_invite_id}")

    @validate_arguments  # type: ignore[operator]
    async def approve(self, user_invite_id: str, approve_data: ElementsUserInviteApprove) -> UserRead:
        """
        Approves a user invite.

        Args:
            user_invite_id: The ID of the user invite to approve.
            approve_data: The approval data for the user invite.

        Returns:
            the approved user invite.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__user_invites.post(
            f"/{user_invite_id}/approve",
            model=UserRead,
            json=approve_data,
        )
