from pydantic import BaseModel, Extra, Field


class UserRoleCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    role: str = Field(
        ...,
        description="the role that will be assigned (accepts either the role id or the role key)",
        title="Role",
    )
    tenant: str = Field(
        ...,
        description="the tenant the role is associated with (accepts either the tenant id or the tenant key)",
        title="Tenant",
    )
