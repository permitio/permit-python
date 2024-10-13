from typing import Dict, List, Optional

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Field
else:
    from pydantic.v1 import BaseModel, Field  # type: ignore

JWT = str


class UserKey(BaseModel):
    key: str


class AssignedRole(BaseModel):
    role: str  # role key
    tenant: str  # tenant key


class UserInput(UserKey):
    first_name: Optional[str] = Field(None, alias="firstName")
    last_name: Optional[str] = Field(None, alias="lastName")
    email: Optional[str] = None
    roles: Optional[List[AssignedRole]] = None
    attributes: Optional[Dict] = None


class ResourceInput(BaseModel):
    type: str  # namespace/type of resources/objects
    id: Optional[str] = None  # id of individual object
    key: Optional[str] = None  # key of individual object
    tenant: Optional[str] = None  # tenant the resource belongs to
    attributes: Optional[Dict] = None  # extra resources attributes
    context: Optional[Dict] = None  # extra context


class OpaResult(BaseModel):
    allow: bool


class AuthorizedUserAssignment(BaseModel):
    user: str = Field(..., description="The user that is authorized")
    tenant: str = Field(..., description="The tenant that the user is authorized for")
    resource: str = Field(..., description="The resource that the user is authorized for")
    role: str = Field(..., description="The role that the user is assigned to")


AuthorizedUsersDict = Dict[str, List[AuthorizedUserAssignment]]


class AuthorizedUsersResult(BaseModel):
    resource: str = Field(
        ...,
        description="The resource that the result is about."
        "Can be either 'resource:*' or 'resource:resource_instance'",
    )
    tenant: str = Field(..., description="The tenant that the result is about")
    users: AuthorizedUsersDict = Field(
        ...,
        description="A key value mapping of the users that are "
        "authorized for the resource."
        "The key is the user key and the value is a list of assignments allowing the user to perform"
        "the requested action",
    )
