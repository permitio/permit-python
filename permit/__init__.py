"""Permit.io SDK: authorization checks and the Permit REST API from Python.

The `X as X` imports mark the package's public names as explicit re-exports
for type checkers.
"""

from permit.api.models import *  # noqa: F403 - every API model is part of the public surface
from permit.config import PermitConfig as PermitConfig
from permit.enforcement.enforcer import Action as Action
from permit.enforcement.enforcer import Resource as Resource
from permit.enforcement.enforcer import User as User
from permit.enforcement.interfaces import AssignedRole as AssignedRole
from permit.enforcement.interfaces import AuthorizedUsersResult as AuthorizedUsersResult
from permit.enforcement.interfaces import ResourceInput as ResourceInput
from permit.enforcement.interfaces import UserInput as UserInput
from permit.exceptions import PermitAlreadyExistsError as PermitAlreadyExistsError
from permit.exceptions import PermitApiDetailedError as PermitApiDetailedError
from permit.exceptions import PermitApiError as PermitApiError
from permit.exceptions import PermitConnectionError as PermitConnectionError
from permit.exceptions import PermitContextChangeError as PermitContextChangeError
from permit.exceptions import PermitContextError as PermitContextError
from permit.exceptions import PermitError as PermitError

# Deprecated, but still exported for existing callers.
from permit.exceptions import PermitException as PermitException  # type: ignore[deprecated]
from permit.exceptions import PermitNotFoundError as PermitNotFoundError
from permit.exceptions import PermitValidationError as PermitValidationError
from permit.permit import Permit as Permit
from permit.utils.context import Context as Context
