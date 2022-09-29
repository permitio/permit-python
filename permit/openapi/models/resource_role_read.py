from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class ResourceRoleRead(BaseModel):
    class Config:
        extra = Extra.forbid

    name: str = Field(..., description="The name of the role", title="Name")
    description: Optional[str] = Field(
        None,
        description="optional description string explaining what this role represents, or what permissions are granted to it.",
        title="Description",
    )
    permissions: Optional[List[str]] = Field(
        None,
        description="list of action keys that define what actions this resource role is permitted to do",
        title="Permissions",
    )
    extends: Optional[List[str]] = Field(
        None,
        description="list of role keys that define what roles this role extends. In other words: this role will automatically inherit all the permissions of the given roles in this list.",
        title="Extends",
    )
    key: str = Field(
        ...,
        description="A URL-friendly name of the role (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the role.",
        title="Key",
    )
    id: UUID = Field(..., description="Unique id of the role", title="Id")
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the role belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the role belongs to.",
        title="Project Id",
    )
    environment_id: UUID = Field(
        ...,
        description="Unique id of the environment that the role belongs to.",
        title="Environment Id",
    )
    resource_id: UUID = Field(
        ...,
        description="Unique id of the resource that the role belongs to.",
        title="Resource Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the role was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the role was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
