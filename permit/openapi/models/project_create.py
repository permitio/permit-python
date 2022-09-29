from typing import Any, Dict, Optional

from pydantic import BaseModel, Extra, Field


class ProjectCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A URL-friendly name of the project (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the project.",
        title="Key",
    )
    name: str = Field(..., description="The name of the project", title="Name")
    description: Optional[str] = Field(
        None,
        description="a longer description outlining the project objectives",
        title="Description",
    )
    settings: Optional[Dict[str, Any]] = Field(
        None, description="the settings for this project", title="Settings"
    )
