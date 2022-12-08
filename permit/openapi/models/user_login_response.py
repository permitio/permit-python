from pydantic import BaseModel, Field


class UserLoginResponse(BaseModel):
    token: str = Field(..., description="The token to redirect to", title="Token")
    redirect_url: str = Field(
        ...,
        description="The full URL to which the user should be redirected in order to complete the login process",
        title="Redirect Url",
    )
