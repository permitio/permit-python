from typing import Optional

from pydantic import BaseModel, Extra, Field

from permit.openapi.models.attribute_type import AttributeType


class AttributeBlock(BaseModel):
    class Config:
        extra = Extra.forbid

    type: AttributeType = Field(
        ...,
        description="The type of the attribute, we currently support: `bool`, `number` (ints, floats), `time` (a timestamp), `string`, and `json`.",
    )
    description: Optional[str] = Field(
        None,
        description="optional description string explaining what data this attribute will store",
        title="Description",
    )
