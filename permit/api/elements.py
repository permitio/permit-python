from typing import TYPE_CHECKING
from uuid import UUID

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import BaseModel, Extra, Field
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Extra, Field
else:
    from pydantic.v1 import BaseModel, Extra, Field

from permit.api.base import BasePermitApi
from permit.config import PermitConfig
from permit.utils.sync import SyncClass


class EmbeddedLoginRequestOutput(BaseModel):
    """The API's answer to an Elements login request."""

    class Config:
        extra = Extra.allow

    error: str | None = Field(
        default=None,
        description="If the login request failed, this field will contain the error message",
        title="Error",
    )
    error_code: int | None = Field(
        default=None,
        description="If the login request failed, this field will contain the error code",
        title="Error Code",
    )
    token: str | None = Field(
        default=None,
        description="The auth token that lets your users login into permit elements",
        title="Token",
    )
    extra: str | None = Field(
        default=None,
        description="Extra data that you can pass to the login request",
        title="Extra",
    )
    redirect_url: str = Field(
        ...,
        description="The full URL to which the user should be redirected "
        "in order to complete the login process",
        title="Redirect Url",
    )


class LoginAsSchema(BaseModel):
    """Represents the schema for the loginAs request."""

    user_id: str = Field(..., description="The key (or ID) of the user the element will log in as.")
    tenant_id: str = Field(
        ...,
        description="The key (or ID) of the active tenant for the logged in user."
        "The embedded user will only be able to access the active tenant.",
    )


class UserLoginAsResponse(EmbeddedLoginRequestOutput):
    """The result of `ElementsApi.login_as()`."""

    # Bare `dict` on purpose: pydantic v1 passes it through as is, while a parameterized
    # dict would be validated as a mapping and copied.
    content: dict | None = Field(  # type: ignore[type-arg]
        None,
        description="Content to return in the response body for header/bearer login",
    )


class ElementsApi(BasePermitApi):
    """Log users into Permit Elements (embeddable UI components)."""

    def __init__(self, config: PermitConfig) -> None:
        super().__init__(config)
        self.__auth = self._build_http_client("/v2/auth")

    async def login_as(self, user_id: str | UUID, tenant_id: str | UUID) -> UserLoginAsResponse:
        """Log a user into Permit Elements, in the context of a tenant.

        Args:
            user_id: The key or ID of the user to log in as.
            tenant_id: The key or ID of the tenant the user will be able to access.

        Returns:
            The login ticket, including the URL that completes the login.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
        """
        if isinstance(user_id, UUID):
            user_id = str(user_id)
        if isinstance(tenant_id, UUID):
            tenant_id = str(tenant_id)
        ticket = await self.__auth.post(
            "/elements_login_as",
            model=EmbeddedLoginRequestOutput,
            json=LoginAsSchema(user_id=user_id, tenant_id=tenant_id),
        )
        return UserLoginAsResponse(**ticket.dict(), content={"url": ticket.redirect_url})


class SyncElementsApi(ElementsApi, metaclass=SyncClass):
    """Blocking variant of `ElementsApi`."""
