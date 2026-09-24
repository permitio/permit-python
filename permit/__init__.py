"""Permit.io SDK: authorization checks and the Permit REST API from Python.

The `X as X` imports mark the package's public names as explicit re-exports
for type checkers.
"""

import warnings as _warnings

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
from permit.exceptions import PermitException as PermitException
from permit.exceptions import PermitNotFoundError as PermitNotFoundError
from permit.exceptions import PermitValidationError as PermitValidationError
from permit.permit import Permit as Permit
from permit.utils.context import Context as Context
from permit.utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    # Importing any permit module runs this file first, and only once per process, so this
    # warns once. stacklevel=2 attributes the warning to the code that imported permit (the
    # import machinery's frames are skipped), which Python shows by default when that is
    # __main__.
    _warnings.warn(
        "Support for pydantic 1 is deprecated and will be removed in permit 4.0. Upgrade to pydantic 2.",
        DeprecationWarning,
        stacklevel=2,
    )
