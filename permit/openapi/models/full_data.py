from typing import Dict

from pydantic import BaseModel, Field

from permit.openapi.models.role_data import RoleData
from permit.openapi.models.user_data import UserData


class FullData(BaseModel):
    users: Dict[str, UserData] = Field(..., title="Users")
    roles: Dict[str, RoleData] = Field(..., title="Roles")
