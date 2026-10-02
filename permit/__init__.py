"""Permit.io SDK: authorization checks and the Permit REST API from Python.

The `X as X` imports mark the package's public names as explicit re-exports
for type checkers.
"""

import typing as _typing
import warnings as _warnings

from permit.api.models import *  # noqa: F403 - every API model is part of the public surface
from permit.config import PermitConfig as PermitConfig
from permit.enforcement.enforcer import Action as Action
from permit.enforcement.enforcer import Resource as Resource
from permit.enforcement.enforcer import User as User
from permit.enforcement.interfaces import AssignedRole as AssignedRole
from permit.enforcement.interfaces import AuthorizedUsersResult as AuthorizedUsersResult
from permit.enforcement.interfaces import ResourceInput as ResourceInput
from permit.enforcement.interfaces import TenantDetails as TenantDetails
from permit.enforcement.interfaces import UserInput as UserInput
from permit.exceptions import _PERMIT_EXCEPTION_DEPRECATION, _PermitException
from permit.exceptions import PermitAlreadyExistsError as PermitAlreadyExistsError
from permit.exceptions import PermitApiDetailedError as PermitApiDetailedError
from permit.exceptions import PermitApiError as PermitApiError
from permit.exceptions import PermitConnectionError as PermitConnectionError
from permit.exceptions import PermitContextChangeError as PermitContextChangeError
from permit.exceptions import PermitContextError as PermitContextError
from permit.exceptions import PermitError as PermitError
from permit.exceptions import PermitNotFoundError as PermitNotFoundError
from permit.exceptions import PermitValidationError as PermitValidationError
from permit.permit import Permit as Permit
from permit.utils.context import Context as Context
from permit.utils.deprecation import _warn_deprecated_name
from permit.utils.pydantic_version import PYDANTIC_VERSION as _PYDANTIC_VERSION

if _typing.TYPE_CHECKING:
    # Deprecated, but still exported for existing callers: __getattr__ below serves it.
    from permit.exceptions import PermitException as PermitException  # type: ignore[deprecated]

if _PYDANTIC_VERSION < (2, 0):
    # Importing any permit module runs this file first, and only once per process, so this
    # warns once. stacklevel=2 attributes the warning to the code that imported permit (the
    # import machinery's frames are skipped), which Python shows by default when that is
    # __main__.
    _warnings.warn(
        "Support for pydantic 1 is deprecated and will be removed in permit 4.0. "
        "Upgrade to pydantic 2.",
        DeprecationWarning,
        stacklevel=2,
    )


def _getattr(name: str) -> object:
    """Serve the deprecated `PermitException`, with its warning, to code that reads it."""
    if name == "PermitException":
        _warn_deprecated_name(_PERMIT_EXCEPTION_DEPRECATION)
        return _PermitException
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


if not _typing.TYPE_CHECKING:
    # The module __getattr__ (PEP 562), out of type checkers' sight like permit.exceptions' one.
    __getattr__ = _getattr
