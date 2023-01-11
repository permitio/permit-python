from __future__ import annotations

from typing import Any, Final, Type, Union

from permit.exceptions.base import (
    DETAIL_KEY,
    ERROR_CODE_KEY,
    ErrorCode,
    ErrorType,
    PermitException,
)
from permit.openapi.api.utils import APIErrorDict
from permit.openapi.models import HTTPValidationError


class PermitNotFound(PermitException):
    error_code: ErrorCode = ErrorCode.NOT_FOUND
    type: ErrorType = ErrorType.INVALID_REQUEST_ERROR
    details = "we could not find '{object_type}' object with the key '{object_name}'"

    def __init__(self, object_type: str, object_name: str, *args, **kwargs):
        super().__init__(
            details=self.details.format(
                object_type=object_type,
                object_name=object_name,
            ),
            type=self.type,
            error_code=self.error_code
        )


class PermitContextError(PermitException):
    error_code: ErrorCode = ErrorCode.NOT_FOUND
    type: ErrorType = ErrorType.INVALID_REQUEST_ERROR
    details: str = "error changing context - make sure the given context fits your API key origin"

    def __init__(self, details: str, *args, **kwargs):
        super().__init__(
            details=self.details,
            type=self.type,
            error_code=self.error_code,
        )


class PermitForbidden(PermitException):
    error_code = ErrorCode.FORBIDDEN_ACCESS
    type: ErrorType = ErrorType.INVALID_REQUEST_ERROR
    detail = "we could not let you access to the '{object_type}' object with the key '{object_name}'"

    def __init__(self, object_type, object_name):
        super().__init__(
            details=self.details.format(
                object_type=object_type,
                object_name=object_name,
            ),
            type=self.type,
            error_code=self.error_code,
        )


class PermitConnectionError(PermitException):
    """Permit connection exception"""


class PermitExceptionFactory(PermitException):
    __exceptions_mappings: Final[dict[ErrorCode, Type[PermitException]]] = {
        ErrorCode.UNEXPECTED_ERROR: PermitException,
        ErrorCode.FORBIDDEN_ACCESS: PermitForbidden,
        ErrorCode.NOT_FOUND: PermitNotFound,
    }

    def __new__(cls, error_code: ErrorCode, *args, **kwargs) -> PermitException:
        return cls.__exceptions_mappings[error_code](*args, **kwargs)


def raise_for_error(
    res: Union[HTTPValidationError, None, Any],
    message: str = "error getting response",
    allow_none: bool = False,
    **kwargs,
):
    if res is None and not allow_none:
        raise PermitException(message)
    elif isinstance(res, APIErrorDict):
        error_code_key = ErrorCode.UNEXPECTED_ERROR
        if res_code := res.get(ERROR_CODE_KEY):
            error_code_key = res_code
        else:
            if res_details := res.get(DETAIL_KEY):
                if "forbidden" in res_details.lower():
                    error_code_key = ErrorCode.FORBIDDEN_ACCESS
        raise PermitExceptionFactory(
            error_code_key,
            object_type=kwargs.get("object_type"),
            object_name=kwargs.get("object_name"),
        )
    elif isinstance(res, HTTPValidationError):
        raise PermitException(details=message + f" {res}")


def raise_for_error_by_action(
    res: Union[HTTPValidationError, None, Any],
    object_name: str,
    payload: str,
    action: str = "get",
    **kwargs,
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
            object_type=object_name,
        )
    else:
        raise_for_error(
            res,
            message=f"could not {action} {object_name} with key '{payload}'",
            allow_none=False,
        )
