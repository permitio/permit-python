from typing import Any, Dict, Optional

from pydantic import BaseModel, Extra, Field


class OrganizationUpdate(BaseModel):
    class Config:
        extra = Extra.ignore

    name: Optional[str] = Field(
        None,
        description="The name of the organization, usually it's your company's name.",
        title="Name",
    )
    settings: Optional[Dict[str, Any]] = Field(
        None, description="the settings for this project", title="Settings"
    )
