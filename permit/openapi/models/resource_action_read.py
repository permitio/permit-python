from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class ResourceActionRead(BaseModel):
    class Config:
        extra = Extra.forbid

    name: str = Field(..., description="The name of the action", title="Name")
    description: Optional[str] = Field(
        None,
        description="An optional longer description of what this action respresents in your system",
        title="Description",
    )
    key: str = Field(
        ...,
        description="A URL-friendly name of the action (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the action.",
        title="Key",
    )
    id: UUID = Field(..., description="Unique id of the action", title="Id")
    permission_name: str = Field(
        ...,
        description="The name of the action, prefixed by the resource the action is acting upon.",
        title="Permission Name",
    )
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the action belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the action belongs to.",
        title="Project Id",
    )
    environment_id: UUID = Field(
        ...,
        description="Unique id of the environment that the action belongs to.",
        title="Environment Id",
    )
    resource_id: UUID = Field(
        ...,
        description="Unique id of the resource that the action belongs to.",
        title="Resource Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the action was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the action was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
