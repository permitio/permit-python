from typing import Optional

from pydantic import BaseModel, Extra, Field


class ResourceActionCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A URL-friendly name of the action (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the action.",
        title="Key",
    )
    name: str = Field(..., description="The name of the action", title="Name")
    description: Optional[str] = Field(
        None,
        description="An optional longer description of what this action respresents in your system",
        title="Description",
    )
