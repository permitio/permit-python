from __future__ import annotations

from typing import Any, Final, Type, Union

from permit.exceptions.base import (
    ERROR_CODE_KEY,
    ErrorCode,
    ErrorType,
    PermitException,
    ServiceException,
)
from permit.openapi.api.utils import APIErrorDict
from permit.openapi.models import HTTPValidationError


class PermitNotFound(ServiceException):
    title = "We could not find the requested object/s"
    error_code: ErrorCode = ErrorCode.NOT_FOUND
    type: ErrorType = ErrorType.INVALID_REQUEST_ERROR
    reassurance = "The requested data could not be found"
    explanation = "we could not find '{object_type}' object with the key '{object_name}'"  # TODO: ADD filters to explaination -"with the given filters{filters}"
    suggestion: str = "Please try again with different filters"
    way_out: str = (
        "If you are sure there is an object with the given filters, "
        "contact our support on Slack for further guidance"
    )

    def __init__(self, object_type: str, object_name: str, **kwargs):
        super().__init__(
            explanation=self.explanation.format(
                object_type=object_type,
                object_name=object_name,
            ),
            **kwargs,
        )


class PermitContextException(ServiceException):
    title = "Your context"
    error_code: ErrorCode = ErrorCode.NOT_FOUND
    type: ErrorType = ErrorType.INVALID_REQUEST_ERROR
    reassurance = "The requested data could not be found"
    explanation = "we could not find '{object_type}' object with the key '{object_name}'"  # TODO: ADD filters to explaination -"with the given filters{filters}"
    suggestion: str = "Please try again with different filters"
    way_out: str = (
        "If you are sure there is an object with the given filters, "
        "contact our support on Slack for further guidance"
    )

    def __init__(self, object_type: str, object_name: str, **kwargs):
        super().__init__(
            explanation=self.explanation.format(
                object_type=object_type,
                object_name=object_name,
            ),
            **kwargs,
        )


class PermitConnectionError(ServiceException):
    """Permit connection exception"""


class PermitExceptionFactory(ServiceException):
    __exceptions_mappings: Final[dict[ErrorCode, Type[PermitException]]] = {
        ErrorCode.UNEXPECTED_ERROR: PermitException,
        ErrorCode.NOT_FOUND: PermitNotFound,
    }

    def __new__(cls, error_code: ErrorCode, *args, **kwargs) -> PermitException:
        return cls.__exceptions_mappings[error_code](*args, **kwargs)


def raise_for_error(
    res: Union[HTTPValidationError, None, Any],
    message: str = "error getting response",
    allow_none: bool = False,
):
    if res is None and not allow_none:
        raise PermitException(message)
    elif isinstance(res, APIErrorDict):
        raise PermitExceptionFactory(res[ERROR_CODE_KEY], message=message)
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
