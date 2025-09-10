from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from .base import (
    BasePermitApi,
    SimpleHttpClient,
)
from .context import ApiContextLevel, ApiKeyAccessLevel
from .models import (
    ElementsUserInviteApprove,
    ElementsUserInviteRead,
)


class UserInvitesApi(BasePermitApi):
    @property
    def __user_invites(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/user_invites"
        )

    @validate_arguments  # type: ignore[operator]
    async def approve(self, user_invite_id: str, approve_data: ElementsUserInviteApprove) -> ElementsUserInviteRead:
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
            model=ElementsUserInviteRead,
            json=approve_data,
        )
