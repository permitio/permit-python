from typing import Optional

from pydantic import BaseModel, Extra, Field

from permit.openapi.models.attribute_type import AttributeType


class ResourceAttributeUpdate(BaseModel):
    class Config:
        extra = Extra.forbid

    type: Optional[AttributeType] = Field(
        None,
        description="The type of the attribute, we currently support: `bool`, `number` (ints, floats), `time` (a timestamp), `string`, and `json`.",
    )
    description: Optional[str] = Field(
        None,
        description="An optional longer description of what this attribute respresents in your system",
        title="Description",
    )
