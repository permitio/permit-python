from typing import TYPE_CHECKING, Optional, Union
from uuid import UUID

from ..utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import BaseModel, Extra, Field
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Extra, Field
else:
    from pydantic.v1 import BaseModel, Extra, Field

from ..config import PermitConfig
from ..utils.sync import SyncClass
from .base import BasePermitApi


class EmbeddedLoginRequestOutput(BaseModel):
    class Config:
        extra = Extra.allow

    error: Optional[str] = Field(
        default=None,
        description="If the login request failed, this field will contain the error message",
        title="Error",
    )
    error_code: Optional[int] = Field(
        default=None,
        description="If the login request failed, this field will contain the error code",
        title="Error Code",
    )
    token: Optional[str] = Field(
        default=None,
        description="The auth token that lets your users login into permit elements",
        title="Token",
    )
    extra: Optional[str] = Field(
        default=None,
        description="Extra data that you can pass to the login request",
        title="Extra",
    )
    redirect_url: str = Field(
        ...,
        description="The full URL to which the user should be redirected in order to complete the login process",
        title="Redirect Url",
    )


class LoginAsSchema(BaseModel):
    """
    Represents the schema for the loginAs request.
    """

    user_id: str = Field(..., description="The key (or ID) of the user the element will log in as.")
    tenant_id: str = Field(
        ...,
        description="The key (or ID) of the active tenant for the logged in user."
        + "The embedded user will only be able to access the active tenant.",
    )


class UserLoginAsResponse(EmbeddedLoginRequestOutput):
    content: Optional[dict] = Field(
        default=None,
        description="Content to return in the response body for header/bearer login",
    )


class ElementsApi(BasePermitApi):
    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__auth = self._build_http_client("/v2/auth")

    async def login_as(self, user_id: Union[str, UUID], tenant_id: Union[str, UUID]) -> UserLoginAsResponse:
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


# Type checkers read this class from a generated stub: the SyncClass metaclass
# makes its methods blocking at runtime, which they cannot see.
if TYPE_CHECKING:
    from permit._sync_types import SyncElementsApi as SyncElementsApi
else:

    class SyncElementsApi(ElementsApi, metaclass=SyncClass):
        pass
