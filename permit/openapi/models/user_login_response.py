from pydantic import BaseModel, Field


class UserLoginResponse(BaseModel):
    token: str = Field(..., description="The auth token that lets your users login into permit elements", title="Token")
    redirect_url: str = Field(
        ...,
        description="The full URL to which the user should be redirected in order to complete the login process",
        title="Redirect Url",
    )
