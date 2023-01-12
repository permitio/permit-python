from typing import Optional

from pydantic import BaseModel, Field


class UserLoginResponse(BaseModel):
    error: Optional[str] = Field(
        None,
        description="If the login request failed, this field will contain the error message",
    )
    token: Optional[str] = Field(
        description="The auth token that lets your users login into permit elements"
    )
    extra: Optional[str] = Field(
        None, description="Extra data that you can pass to the login request"
    )
    redirect_url: str = Field(
        description="The full URL to which the user should be redirected in order to complete the login process"
    )


class UserLoginAsResponse(UserLoginResponse):
    content: Optional[dict] = Field(
        None,
        description="Content to return in the response body for header/bearer login",
    )
