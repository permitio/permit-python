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


class AuthorizedUserAssignment(BaseModel):
    user: str = Field(..., description="The user that is authorized")
    tenant: str = Field(..., description="The tenant that the user is authorized for")
    resource: str = Field(
        ..., description="The resource that the user is authorized for"
    )
    role: str = Field(..., description="The role that the user is assigned to")


AuthorizedUsersDict = dict[str, list[AuthorizedUserAssignment]]


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
