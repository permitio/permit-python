from typing import Optional

from pydantic import BaseModel, Extra, Field

from permit.openapi.models.attribute_type import AttributeType


class ResourceAttributeCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A URL-friendly name of the attribute (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the attribute.",
        title="Key",
    )
    type: AttributeType = Field(
        ...,
        description="The type of the attribute, we currently support: `bool`, `number` (ints, floats), `time` (a timestamp), `string`, and `json`.",
    )
    description: Optional[str] = Field(
        None,
        description="An optional longer description of what this attribute respresents in your system",
        title="Description",
    )
