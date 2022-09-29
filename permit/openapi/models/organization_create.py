from typing import Any, Dict, Optional

from pydantic import BaseModel, Extra, Field


class OrganizationCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A URL-friendly name of the organization (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the organization.",
        title="Key",
    )
    name: str = Field(
        ...,
        description="The name of the organization, usually it's your company's name.",
        title="Name",
    )
    settings: Optional[Dict[str, Any]] = Field(
        None, description="the settings for this project", title="Settings"
    )
