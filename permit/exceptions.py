from typing import Any, Union

from permit.openapi.models import HTTPValidationError


class PermitException(Exception):
    """Permit base exception"""


class PermitConnectionError(PermitException):
    """Permit connection exception"""


def raise_for_error(
    res: Union[HTTPValidationError, None, Any],
    message: str = "error getting response",
    allow_none: bool = False,
):
    if res is None and not allow_none:
        raise PermitException(message)
    elif isinstance(res, HTTPValidationError):
        raise PermitException(message + f" {res}")


def raise_for_error_by_action(
    res: Union[HTTPValidationError, None, Any],
    object_name: str,
    payload: str,
    action: str = "get",
):
    if action == "delete":
        raise_for_error(
            res,
            message=f"could not {action} {object_name} with key '{payload}'",
            allow_none=True,
        )
    elif action in ("create", "update", "remove"):
        raise_for_error(
            res,
            message=f"could not {action} {object_name} with: {payload}",
            allow_none=False,
        )
    else:
        raise_for_error(
            res,
            message=f"could not {action} {object_name} with key '{payload}'",
            allow_none=False,
        )
