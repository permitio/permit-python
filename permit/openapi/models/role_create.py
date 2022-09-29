from typing import List, Optional

from pydantic import BaseModel, Extra, Field


class RoleCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A URL-friendly name of the role (i.e: slug). You will be able to query later using this key instead of the id (UUID) of the role.",
        title="Key",
    )
    name: str = Field(..., description="The name of the role", title="Name")
    description: Optional[str] = Field(
        None,
        description="optional description string explaining what this role represents, or what permissions are granted to it.",
        title="Description",
    )
    permissions: Optional[List[str]] = Field(
        None,
        description="list of action keys that define what actions this resource role is permitted to do",
        title="Permissions",
    )
    extends: Optional[List[str]] = Field(
        None,
        description="list of role keys that define what roles this role extends. In other words: this role will automatically inherit all the permissions of the given roles in this list.",
        title="Extends",
    )
