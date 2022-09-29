from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field

from permit.openapi.models.action_block_read import ActionBlockRead
from permit.openapi.models.attribute_block import AttributeBlock
from permit.openapi.models.relations_block import RelationsBlock
from permit.openapi.models.roles_block import RolesBlock


class ResourceRead(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A URL-friendly name of the resource (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the resource.",
        title="Key",
    )
    id: UUID = Field(..., description="Unique id of the resource", title="Id")
    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the resource belongs to.",
        title="Organization Id",
    )
    project_id: UUID = Field(
        ...,
        description="Unique id of the project that the resource belongs to.",
        title="Project Id",
    )
    environment_id: UUID = Field(
        ...,
        description="Unique id of the environment that the resource belongs to.",
        title="Environment Id",
    )
    created_at: datetime = Field(
        ...,
        description="Date and time when the resource was created (ISO_8601 format).",
        title="Created At",
    )
    updated_at: datetime = Field(
        ...,
        description="Date and time when the resource was last updated/modified (ISO_8601 format).",
        title="Updated At",
    )
    name: str = Field(..., description="The name of the resource", title="Name")
    urn: Optional[str] = Field(
        None,
        description="The [URN](https://en.wikipedia.org/wiki/Uniform_Resource_Name) (Uniform Resource Name) of the resource",
        title="Urn",
    )
    description: Optional[str] = Field(
        None,
        description="An optional longer description of what this resource respresents in your system",
        title="Description",
    )
    actions: Dict[str, ActionBlockRead] = Field(
        ...,
        description="\n    A actions definition block, typically contained within a resource type definition block.\n    The actions represents the ways you can interact with a protected resource.\n    ",
        title="Actions",
    )
    attributes: Optional[Dict[str, AttributeBlock]] = Field(
        {},
        description="Attributes that each resource of this type defines, and can be used in your ABAC policies.",
        title="Attributes",
    )
    roles: Optional[RolesBlock] = Field(
        {},
        description="Roles defined on this resource. The key is the role name, and the value contains the role properties such as granted permissions, base roles, etc.",
        title="Roles",
    )
    relations: Optional[RelationsBlock] = Field(
        {},
        description="Relations to other resources. The key is the relation name, and the value is the destination resource.",
        title="Relations",
    )
