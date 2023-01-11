from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field, constr


class ProjectCreate(BaseModel):
    class Config:
        extra = Extra.ignore

    key: str = Field(
        ...,
        description="A URL-friendly name of the project (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the project.",
        title="Key",
    )
    urn_namespace: Optional[constr(regex=r'[a-z0-9-]{2,}')] = Field(
        None,
        description='Optional namespace for URNs. If empty, URNs will be generated from project key.',
        title='Urn Namespace',
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
    active_policy_repo_id: Optional[UUID] = Field(
        None,
        description='the id of the policy repo to use for this project',
        title='Active Policy Repo Id',
    )


