from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field


class APIKeyScopeRead(BaseModel):
    class Config:
        extra = Extra.forbid

    organization_id: UUID = Field(
        ...,
        description="Unique id of the organization that the api_key belongs to.",
        title="Organization Id",
    )
    project_id: Optional[UUID] = Field(
        None,
        description="Unique id of the project that the api_key belongs to.",
        title="Project Id",
    )
    environment_id: Optional[UUID] = Field(
        None,
        description="Unique id of the environment that the api_key belongs to.",
        title="Environment Id",
    )
