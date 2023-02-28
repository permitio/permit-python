from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class ProjectUpdate(BaseModel):
    class Config:
        extra = Extra.ignore

    name: Optional[str] = Field(
        None, description="The name of the project", title="Name"
    )
    description: Optional[str] = Field(
        None,
        description="a longer description outlining the project objectives",
        title="Description",
    )
    settings: Optional[Dict[str, Any]] = Field(
        None, description="the settings for this project", title="Settings"
    )
    active_policy_repo_id: Optional[UUID] = Field(
        None,
        description="the id of the policy repo to use for this project",
        title="Active Policy Repo Id",
    )
