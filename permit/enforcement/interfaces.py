from typing import NamedTuple
from typing import Optional, Dict, List


JWT = str


class UserKey(NamedTuple):
    key: str


class AssignedRole(NamedTuple):
    role: str  # role key
    tenant: str  # tenant key


class UserInput(UserKey):
    firstName: Optional[str]
    lastName: Optional[str]
    email: Optional[str]
    roles: Optional[List[AssignedRole]]
    attributes: Optional[Dict]


class ResourceInput(NamedTuple):
    type: str  # namespace/type of resources/objects
    id: Optional[str]  # id of individual object
    tenant: Optional[str]  # tenant the resource belongs to
    attributes: Optional[Dict]  # extra resources attributes
    context: Optional[Dict]  # extra context


class OpaResult(NamedTuple):
    allow: bool
