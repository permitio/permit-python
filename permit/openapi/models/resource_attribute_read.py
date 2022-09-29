from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field

from permit.openapi.models.attribute_type import AttributeType


class ResourceAttributeRead(BaseModel):
    class Config:
        extra = Extra.forbid

    type: AttributeType = Field(
        ...,
        description="The type of the attribute, we currently support: `bool`, `number` (ints, floats), `time` (a timestamp), `string`, and `json`.",
    )
    description: Optional[str] = Field(
        None,
        description="An optional longer description of what this attribute respresents in your system",
        title="Description",
    )
    key: str = Field(
        ...,
        description="A URL-friendly name of the attribute (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the attribute.",
        title="Key",
    )
    id: UUID = Field(..., description="Unique id of the attribute", title="Id")
    resource_id: UUID = Field(
        ...,
        description="Unique id of the resource that the attribute belongs to.",
        title="Resource Id",
    )
    resource_key: str = Field(
        ...,
        description="A URL-friendly name of the resource (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the resource.",
        title="Resource Key",
    )
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the attribute belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the attribute belongs to.",
        title="Project Id",
    )
    environment_id: UUID = Field(
        ...,
        description="Unique id of the environment that the attribute belongs to.",
        title="Environment Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the attribute was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the attribute was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
