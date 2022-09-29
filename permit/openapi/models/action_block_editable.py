from typing import Optional

from pydantic import BaseModel, Extra, Field


class ActionBlockEditable(BaseModel):
    class Config:
        extra = Extra.forbid

    name: Optional[str] = Field(
        None, description="a more descriptive name for the action", title="Name"
    )
    description: Optional[str] = Field(
        None,
        description="optional description string explaining what this action represents in your system",
        title="Description",
    )
