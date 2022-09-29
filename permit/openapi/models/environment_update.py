from typing import Optional

from pydantic import BaseModel, Extra, Field


class EnvironmentUpdate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: Optional[str] = Field(
        None,
        description="A URL-friendly name of the environment (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the environment.",
        title="Key",
    )
    name: Optional[str] = Field(
        None, description="The name of the environment", title="Name"
    )
    description: Optional[str] = Field(
        None,
        description="an optional longer description of the environment",
        title="Description",
    )
