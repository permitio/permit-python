from __future__ import annotations

from enum import Enum
from typing import Any, Final

from pydantic import AnyHttpUrl, BaseModel, Field, parse_obj_as, validator

# TODO: check compat


ERROR_CODE_KEY = "error_code"
DETAIL_KEY = "detail"
CONTACT_SUPPORT_PHRASE: Final[str] = "contact our support on Slack for further guidance"


class ErrorCode(str, Enum):
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONTEXT_ERROR = "CONTEXT_ERROR"
    DUPLICATE_ENTITY = "DUPLICATE_ENTITY"
    EMPTY_DECISION_LOGS = "EMPTY_DECISION_LOGS"
    MISSING_REQUEST_ATTRIBUTE = "MISSING_REQUEST_ATTRIBUTE"
    FORBIDDEN_ACCESS = "FORBIDDEN_ACCESS"
    INVALID_PERMISSION_FORMAT = "INVALID_PERMISSION_FORMAT"
    MISSING_PERMISSIONS = "MISSING_PERMISSIONS"
    UNSUPPORTED_ATTRIBUTE_TYPE = "UNSUPPORTED_ATTRIBUTE_TYPE"
    MISSING_RESOURCE_ATTRIBUTE = "MISSING_RESOURCE_ATTRIBUTE"
    INVALID_POLICY_REPO_STATUS = "INVALID_POLICY_REPO_STATUS"
    MISMATCH_ATTRIBUTES_TYPES = "MISMATCH_ATTRIBUTES_TYPES"


class ErrorType(str, Enum):
    GENERAL_ERROR = "general_error"
    API_ERROR = "api_error"
    CACHE_ERROR = "cache_error"
    INVALID_REQUEST_ERROR = "invalid_request_error"


class PermitException(Exception):
    """Permit base exception"""
    error_code: ErrorCode = ErrorCode.UNEXPECTED_ERROR
    type: ErrorType = ErrorType.GENERAL_ERROR
    details: str = "An error occurred within a Permit.io client"

    def __init__(
        self,
        error_code: ErrorCode | None = None,
        type: ErrorType | None = None,
        details: str | None = None,
    ):
        self._override_default_attributes_if_provided(
            error_code,
            type,
            details
        )
        super().__init__()

    @property
    def message(self) -> str:
        return f"Error Type - {self.type}, Error Code - {self.error_code}, Details - {self.details}"

    def __override_default_attribute_if_provided(
        self, attribute_name: str, attribute_value: Any | None
    ):
        if hasattr(self, attribute_name) and attribute_value is not None:
            setattr(self, attribute_name, attribute_value)

    def _override_default_attributes_if_provided(
        self,
        error_code: ErrorCode | None,
        title: str | None,
        info: str | None,
    ) -> None:
        self.__override_default_attribute_if_provided("error_code", error_code)
        self.__override_default_attribute_if_provided("title", title)
        self.__override_default_attribute_if_provided("details", info)
