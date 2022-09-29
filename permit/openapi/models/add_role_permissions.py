from typing import List

from pydantic import BaseModel, Extra, Field


class AddRolePermissions(BaseModel):
    class Config:
        extra = Extra.forbid

    permissions: List[str] = Field(
        ...,
        description='List of permissions to assign to the role. If a permission is already granted to the role it is skipped. Each permission can be either a resource action id, or `{resource_key}:{action_key}`, i.e: the "permission name".',
        title="Permissions",
    )
