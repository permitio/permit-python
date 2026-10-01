from typing import TYPE_CHECKING

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from permit.api.base import BasePermitApi, SimpleHttpClient
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import PDPDataRefreshRequest, PDPDataRefreshResponse


class PdpsApi(BasePermitApi):
    """Act on the Policy Decision Points (PDPs) connected to an environment."""

    @property
    def __pdp_configs(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/pdps/{self.config.api_context.project}/{self.config.api_context.environment}/configs"
        )

    @validate_arguments
    async def refresh(self, reason: str | None = None) -> PDPDataRefreshResponse:
        """Triggers a data refresh on every PDP in the environment.

        Each PDP connected to the environment fetches all of its authorization data from
        Permit again now, instead of at its next periodic update. Use it when the data a PDP
        decides on changed outside Permit, such as in an external data source, and the PDPs
        should not wait for their next update to see it.

        The call returns once Permit has triggered the refresh, not once the PDPs have
        finished it: they fetch the data in the background, so a check sent right after
        this returns may still be answered from the old data.

        Needs an environment-level API key, or a project- or organization-level key with the
        SDK's API context set to the environment. The key needs write or admin access: the
        API rejects a read-only key with 403.

        Args:
            reason: Why the refresh was triggered, at most 512 characters. The PDPs show it
                in their logs.

        Returns:
            The id of the data update that carries the refresh, and the ids of the PDP
            configurations it was sent to.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 403 for a
                read-only API key or 404 when the environment has no PDP configuration.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        request = (
            PDPDataRefreshRequest() if reason is None else PDPDataRefreshRequest(reason=reason)
        )
        return await self.__pdp_configs.post("/refresh", model=PDPDataRefreshResponse, json=request)
