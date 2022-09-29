from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class OrganizationRead(BaseModel):
    class Config:
        extra = Extra.forbid

    id: UUID = Field(..., description="Unique id of the organization", title="Id")
    created_at: datetime = Field(
        ...,
        description="Date and time when the organization was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the organization was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
    key: str = Field(
        ...,
        description="A URL-friendly name of the organization (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the organization.",
        title="Key",
    )
    name: str = Field(
        ...,
        description="The name of the organization, usually it's your company's name.",
        title="Name",
    )
    settings: Optional[Dict[str, Any]] = Field(
        None, description="the settings for this project", title="Settings"
    )
