from pydantic import BaseModel, Extra, Field


class UserRole(BaseModel):
    class Config:
        extra = Extra.forbid

    role: str = Field(..., description="the role that is assigned", title="Role")
    tenant: str = Field(
        ..., description="the tenant the role is associated with", title="Tenant"
    )
