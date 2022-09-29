from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Extra, Field

from permit.openapi.models.user_role import UserRole


class UserRead(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A unique id by which Permit will identify the user for permission checks. You will later pass this ID to the `permit.check()` API. You can use anything for this ID, the user email, a UUID or anything else as long as it's unique on your end. The user key must be url-friendly (slugified).",
        title="Key",
    )
    id: UUID = Field(..., description="Unique id of the user", title="Id")
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the user belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the user belongs to.",
        title="Project Id",
    )
    environment_id: UUID = Field(
        ...,
        description="Unique id of the environment that the user belongs to.",
        title="Environment Id",
    )
    roles: Optional[List[UserRole]] = Field([], title="Roles")
    email: Optional[EmailStr] = Field(
        None,
        description="The email of the user. If synced, will be unique inside the environment.",
        title="Email",
    )
    first_name: Optional[str] = Field(
        None, description="First name of the user.", title="First Name"
    )
    last_name: Optional[str] = Field(
        None, description="Last name of the user.", title="Last Name"
    )
    attributes: Optional[Dict[str, Any]] = Field(
        {},
        description="Arbitraty user attributes that will be used to enforce attribute-based access control policies.",
        title="Attributes",
    )
