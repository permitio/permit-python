from typing import List, Optional

from pydantic import BaseModel, Extra, Field


class RoleBlock(BaseModel):
    class Config:
        extra = Extra.forbid

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
