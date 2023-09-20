from enum import Enum
from typing import Optional, Union
from uuid import UUID

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Field
else:
    from pydantic.v1 import BaseModel, Field  # type: ignore

from ..config import PermitConfig
from ..utils.sync import SyncClass
from .base import BasePermitApi
from .models import EmbeddedLoginRequestOutput


class LoginAsErrorMessages(str, Enum):
    USER_NOT_FOUND = "User not found"
    TENANT_NOT_FOUND = "Tenant not found"
    INVALID_PERMISSION_LEVEL = "Invalid user permission level"
    FORBIDDEN_ACCESS = "Forbidden access"


class LoginAsSchema(BaseModel):
    """
    Represents the schema for the loginAs request.
    """

    user_id: str = Field(
        ..., description="The key (or ID) of the user the element will log in as."
    )
    tenant_id: str = Field(
        ...,
        description="The key (or ID) of the active tenant for the logged in user."
        + "The embedded user will only be able to access the active tenant.",
    )


class UserLoginAsResponse(EmbeddedLoginRequestOutput):
    content: Optional[dict] = Field(
        None,
        description="Content to return in the response body for header/bearer login",
    )


class ElementsApi(BasePermitApi):
    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__auth = self._build_http_client("/v2/auth")

    async def login_as(
        self, user_id: Union[str, UUID], tenant_id: Union[str, UUID]
    ) -> UserLoginAsResponse:
        if isinstance(user_id, UUID):
            user_id = user_id.hex
        if isinstance(tenant_id, UUID):
            tenant_id = tenant_id.hex
        ticket = await self.__auth.post(
            "/elements_login_as",
            model=EmbeddedLoginRequestOutput,
            json=LoginAsSchema(user_id=user_id, tenant_id=tenant_id),
        )
        return UserLoginAsResponse(
            **ticket.dict(), content={"url": ticket.redirect_url}
        )


class SyncElementsApi(ElementsApi, metaclass=SyncClass):
    pass
