from typing import Optional

from pydantic import BaseModel, Extra, Field


class ResourceActionUpdate(BaseModel):
    class Config:
        extra = Extra.forbid

    name: Optional[str] = Field(
        None, description="The name of the action", title="Name"
    )
    description: Optional[str] = Field(
        None,
        description="An optional longer description of what this action respresents in your system",
        title="Description",
    )
