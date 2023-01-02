from __future__ import annotations

from enum import Enum
from typing import Any, Final

from pydantic import AnyHttpUrl, BaseModel, Field, parse_obj_as, validator

# TODO: check compat


ERROR_CODE_KEY = "error_code"
CONTACT_SUPPORT_PHRASE: Final[str] = "contact our support on Slack for further guidance"


class ErrorCode(str, Enum):
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    NOT_FOUND = "NOT_FOUND"
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


class ErrorDetails(BaseModel):
    title: str
    type: ErrorType
    reassurance: str = Field(..., exclude=True)
    explanation: str = Field(..., exclude=True)
    suggestion: str = Field(..., exclude=True)
    way_out: str = Field(..., exclude=True)
    support_link: AnyHttpUrl | None = None
    error_code: ErrorCode
    message: str = ""
    additional_info: Any = None

    @validator("message", always=True)
    def build_message(cls, v: str | None, values: dict[str, Any]):
        if v is not None and v != "":
            return v

        reassurance = values.get("reassurance")
        explanation = values.get("explanation")
        suggestion = values.get("suggestion")
        way_out = values.get("way_out")

        assert reassurance is not None and reassurance != ""
        assert explanation is not None and explanation != ""
        assert suggestion is not None and suggestion != ""
        assert way_out is not None and way_out != ""

        return f"{reassurance}, {explanation}. {suggestion}.\n{way_out}."


class PermitException(Exception):
    """Permit base exception"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args)


class ServiceException(PermitException):
    """
    The base exception for the backend API
    the purpose for this exception class is to make the all the errors returned from the api
    in the same json structure and message structure
    this will return message that looks like:
    reassurance, explanation.suggestion.\nway_out.
    that follows the best practices talked about in this article:
    https://wix-ux.com/when-life-gives-you-lemons-write-better-error-messages-46c5223e1a2f
    """

    error_code: ErrorCode = ErrorCode.UNEXPECTED_ERROR
    title: str = "The request could not be completed"
    type: ErrorType = ErrorType.GENERAL_ERROR
    reassurance: str = "You did nothing wrong"
    explanation: str = (
        "but we could not finish your request due to a technical issue on our end"
    )
    suggestion: str = "Please try again"
    way_out: str = "If the issue keeps happening, " + CONTACT_SUPPORT_PHRASE
    support_link: AnyHttpUrl | None = parse_obj_as(
        AnyHttpUrl, "https://permit-io.slack.com/ssb/redirect"
    )
    _additional_info: Any = None

    def __init__(
        self,
        error_code: ErrorCode | None = None,
        type: ErrorType | None = None,
        title: str | None = None,
        reassurance: str | None = None,
        explanation: str | None = None,
        suggestion: str | None = None,
        way_out: str | None = None,
        support_link: AnyHttpUrl | None = None,
    ):
        self._override_default_attributes_if_provided(
            error_code,
            type,
            title,
            reassurance,
            explanation,
            suggestion,
            way_out,
            support_link,
        )
        super().__init__()

    @property
    def message(self) -> str:
        return self.get_details().message

    def get_details(self) -> ErrorDetails:
        return ErrorDetails(
            title=self.title,
            reassurance=self.reassurance,
            explanation=self.explanation,
            suggestion=self.suggestion,
            way_out=self.way_out,
            support_link=self.support_link,
            error_code=self.error_code,
            additional_info=self._additional_info,
        )

    def __override_default_attribute_if_provided(
        self, attribute_name: str, attribute_value: Any | None
    ):
        if hasattr(self, attribute_name) and attribute_value is not None:
            setattr(self, attribute_name, attribute_value)

    def _override_default_attributes_if_provided(
        self,
        error_code: ErrorCode | None,
        title: str | None,
        reassurance: str | None,
        explanation: str | None,
        suggestion: str | None,
        way_out: str | None,
        support_link: AnyHttpUrl | None,
        status_code: int | None,
    ) -> None:
        self.__override_default_attribute_if_provided("error_code", error_code)
        self.__override_default_attribute_if_provided("title", title)
        self.__override_default_attribute_if_provided("reassurance", reassurance)
        self.__override_default_attribute_if_provided("explanation", explanation)
        self.__override_default_attribute_if_provided("suggestion", suggestion)
        self.__override_default_attribute_if_provided("way_out", way_out)
        self.__override_default_attribute_if_provided("support_link", support_link)
        self.__override_default_attribute_if_provided("status_code", status_code)
