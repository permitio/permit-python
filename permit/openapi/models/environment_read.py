from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class EnvironmentRead(BaseModel):
    class Config:
        extra = Extra.ignore

    id: UUID = Field(..., description="Unique id of the environment", title="Id")
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the environment belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the environment belongs to.",
        title="Project Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the environment was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the environment was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
    key: str = Field(
        ...,
        description="A URL-friendly name of the environment (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the environment.",
        title="Key",
    )
    name: str = Field(..., description="The name of the environment", title="Name")
    description: Optional[str] = Field(
        None,
        description="an optional longer description of the environment",
        title="Description",
    )
    custom_branch_name: Optional[str] = Field(
        None,
        description='when using gitops feature, an optional branch name for the environment',
        title='Custom Branch Name',
    )
