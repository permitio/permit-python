from typing import TYPE_CHECKING, Any, Dict, List  # noqa: UP035 - public alias below

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import BaseModel, Field
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Field
else:
    from pydantic.v1 import BaseModel, Field


class UserKey(BaseModel):
    """A user identified by key only."""

    key: str


class AssignedRole(BaseModel):
    """A role a user holds in a tenant."""

    role: str  # role key
    tenant: str  # tenant key


class UserInput(UserKey):
    """A user as sent to the PDP on an authorization query.

    Both the python field name (``first_name``) and the wire alias (``firstName``)
    populate the field. Serialization always uses the field name, which is the
    spelling the PDP reads.
    """

    class Config:
        allow_population_by_field_name = True

    first_name: str | None = Field(default=None, alias="firstName")
    last_name: str | None = Field(default=None, alias="lastName")
    email: str | None = None
    roles: list[AssignedRole] | None = None
    attributes: dict[Any, Any] | None = None


class ResourceInput(BaseModel):
    """A resource as sent to the PDP on an authorization query."""

    type: str  # namespace/type of resources/objects
    id: str | None = None  # id of individual object
    key: str | None = None  # key of individual object
    tenant: str | None = None  # tenant the resource belongs to
    attributes: dict[Any, Any] | None = None  # extra resources attributes
    context: dict[Any, Any] | None = None  # extra context


class AuthorizedUserAssignment(BaseModel):
    """A role assignment that grants a user the queried permission."""

    user: str = Field(..., description="The user that is authorized")
    tenant: str = Field(..., description="The tenant that the user is authorized for")
    resource: str = Field(..., description="The resource that the user is authorized for")
    role: str = Field(..., description="The role that the user is assigned to")


# Public alias; runtime object kept identical (a `typing` generic, not a builtin one).
AuthorizedUsersDict = Dict[str, List[AuthorizedUserAssignment]]  # noqa: UP006


class AuthorizedUsersResult(BaseModel):
    """The result of an `authorized_users()` query."""

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
        "The key is the user key and the value is a list of assignments "
        "allowing the user to perform"
        "the requested action",
    )
