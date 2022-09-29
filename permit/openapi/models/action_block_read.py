from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class ActionBlockRead(BaseModel):
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
    id: UUID = Field(..., description="Unique id of the action", title="Id")
    key: Optional[str] = Field(None, description="action key", title="Key")
