from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class RoleAssignmentRead(BaseModel):
    class Config:
        extra = Extra.forbid

    id: UUID = Field(..., description="Unique id of the role assignment", title="Id")
    user: str = Field(..., description="the user the role is assigned to", title="User")
    role: str = Field(..., description="the role that is assigned", title="Role")
    tenant: str = Field(
        ..., description="the tenant the role is associated with", title="Tenant"
    )
    user_id: UUID = Field(..., description="Unique id of the user", title="User Id")
    role_id: UUID = Field(..., description="Unique id of the role", title="Role Id")
    tenant_id: UUID = Field(
        ..., description="Unique id of the tenant", title="Tenant Id"
    )
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the role assignment belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the role assignment belongs to.",
        title="Project Id",
    )
    environment_id: UUID = Field(
        ...,
        description="Unique id of the environment that the role assignment belongs to.",
        title="Environment Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the role assignment was created (ISO_8601 format).",
        title="Created At",
    )
