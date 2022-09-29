from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class TenantRead(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A unique id by which Permit will identify the tenant. The tenant key must be url-friendly (slugified).",
        title="Key",
    )
    id: UUID = Field(..., description="Unique id of the tenant", title="Id")
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the tenant belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the tenant belongs to.",
        title="Project Id",
    )
    environment_id: UUID = Field(
        ...,
        description="Unique id of the environment that the tenant belongs to.",
        title="Environment Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the tenant was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the tenant was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
    last_action_at: datetime = Field(
        ...,
        description="Date and time when the tenant was last active (ISO_8601 format). In other words, this is the last time a permission check was done on a resource belonging to this tenant.",
        title="Last Action At",
    )
    name: str = Field(
        ..., description="A descriptive name for the tenant", title="Name"
    )
    description: Optional[str] = Field(
        None,
        description="an optional longer description of the tenant",
        title="Description",
    )
    attributes: Optional[Dict[str, Any]] = Field(
        {},
        description="Arbitraty tenant attributes that will be used to enforce attribute-based access control policies.",
        title="Attributes",
    )
