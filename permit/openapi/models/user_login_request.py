from pydantic import BaseModel, Field


class UserLoginRequest(BaseModel):
    user_id: str = Field(
        ...,
        description="ID or key of the user for whom to generate a token",
        title="User Id",
    )
    tenant_id: str = Field(
        ...,
        description="ID or key of the tenant to which access is requested",
        title="Tenant Id",
    )
