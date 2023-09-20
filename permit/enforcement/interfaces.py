from typing import Dict, List, Optional

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel
else:
    from pydantic.v1 import BaseModel  # type: ignore


JWT = str


class UserKey(BaseModel):
    key: str


class AssignedRole(BaseModel):
    role: str  # role key
    tenant: str  # tenant key


class UserInput(UserKey):
    firstName: Optional[str]
    lastName: Optional[str]
    email: Optional[str]
    roles: Optional[List[AssignedRole]]
    attributes: Optional[Dict]


class ResourceInput(BaseModel):
    type: str  # namespace/type of resources/objects
    id: Optional[str]  # id of individual object
    key: Optional[str]  # key of individual object
    tenant: Optional[str]  # tenant the resource belongs to
    attributes: Optional[Dict]  # extra resources attributes
    context: Optional[Dict]  # extra context


class OpaResult(BaseModel):
    allow: bool
