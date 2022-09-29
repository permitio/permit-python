from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class ProjectRead(BaseModel):
    class Config:
        extra = Extra.forbid

    id: UUID = Field(..., description="Unique id of the project", title="Id")
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the project belongs to.",
        title="Organization Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the project was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the project was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
    key: str = Field(
        ...,
        description="A URL-friendly name of the project (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the project.",
        title="Key",
    )
    name: str = Field(..., description="The name of the project", title="Name")
    description: Optional[str] = Field(
        None,
        description="a longer description outlining the project objectives",
        title="Description",
    )
    settings: Optional[Dict[str, Any]] = Field(
        None, description="the settings for this project", title="Settings"
    )
