import functools
from typing import Optional

import aiohttp
from loguru import logger
from typing_extensions import deprecated

from permit.utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import ValidationError
else:
    from pydantic.v1 import ValidationError  # type: ignore[assignment]

from permit.api.models import ErrorDetails, HTTPValidationError

DEFAULT_SUPPORT_LINK = "https://permit-io.slack.com/ssb/redirect"


class PermitError(Exception):
    """Permit base exception"""


@deprecated("Use PermitError instead")
class PermitException(PermitError):  # noqa: N818
    """Permit base exception (deprecated, use PermitError instead)"""


class PermitConnectionError(PermitException):
    """Permit connection exception"""

    def __init__(self, message: str, *, error: Optional[aiohttp.ClientError] = None):
        super().__init__(message)
        self.original_error = error


class PermitContextError(PermitError):
    """
    The `PermitContextError` class represents an error that occurs when an API method
    is called with insufficient context (not knowing in what environment, project or
    organization the API call is being made).

    Some of the input for the API method is provided via the SDK context.
    If the context is missing some data required for a method - the api call will fail.
    """


class PermitContextChangeError(PermitError):
    """
    The `PermitContextChangeError` will be thrown when the user is trying to set the
    SDK context to an object that the current API Key cannot access (and if allowed,
    such api calls will result is 401). Instead, the SDK throws this exception.
    """


class PermitApiError(PermitError):
    """
    Wraps an error HTTP Response that occurred during a Permit REST API request.
    """

    def __init__(
        self,
        response: aiohttp.ClientResponse,
        body: Optional[dict] = None,
    ):
        super().__init__()
        self._response = response
        self._body = body

    def _get_message(self) -> str:
        return f"{self.status_code} API Error: {self.details}"

    def __str__(self):
        return self._get_message()

    @property
    def message(self) -> str:
        return self._get_message()

    @property
    def response(self) -> aiohttp.ClientResponse:
        """
        Get the HTTP response that returned an error status code

        Returns:
            The HTTP response object.
        """
        return self._response

    @property
    def details(self) -> Optional[dict]:
        """
        Get the HTTP response JSON body. Contains details about the error.

        Returns:
            The HTTP response json. If no content will return None.
        """
        return self._body

    @property
    def request_url(self) -> str:
        """
        Get the HTTP request URL that caused the error code.

        Returns:
            The HTTP request url
        """
        return str(self._response.url)

    @property
    def status_code(self) -> int:
        """
        Get the HTTP response status code

        Returns:
            The status code returned.
        """
        return self._response.status

    @property
    def content_type(self) -> Optional[str]:
        """
        Get the HTTP content type header of the error response.

        Returns:
            The value of the HTTP Response Content-type header, or None
        """
        return self._response.headers.get("content-type")


class PermitValidationError(PermitApiError):
    """
    Validation error response from the Permit API.
    """

    def __init__(self, response: aiohttp.ClientResponse, content: HTTPValidationError, body: dict):
        self._content = content
        super().__init__(response, body)

    def _get_message(self) -> str:
        message = "Validation error\n"
        for error in self.content.detail or []:
            location = " -> ".join(str(loc) for loc in error.loc)
            message += f"{location}\n\t{error.msg} ({error.type})\n"

        return message

    @property
    def content(self) -> HTTPValidationError:
        return self._content


class PermitApiDetailedError(PermitApiError):
    """
    Detailed error response from the Permit API.
    """

    def __init__(self, response: aiohttp.ClientResponse, content: ErrorDetails, body: dict):
        self._content = content
        super().__init__(response, body)

    def _get_message(self) -> str:
        message = f"{self.content.title} ({self.content.error_code})\n"
        if self.content.message:
            split_message = self.content.message.replace(". ", ".\n")
            message += f"{split_message}\n"
        message += f"For more information: {self.support_link} (Request ID: {self.id})"
        return message

    @property
    def content(self) -> ErrorDetails:
        return self._content

    @property
    def id(self) -> str:
        return self.content.id

    @property
    def code(self) -> str:
        return self.content.error_code.value

    @property
    def title(self) -> str:
        return self.content.title

    @property
    def explanation(self) -> str:
        return self.content.message or "No further explanation provided"

    @property
    def support_link(self) -> str:
        return str(self.content.support_link or DEFAULT_SUPPORT_LINK)

    @property
    def additional_info(self):
        return self.content.additional_info


class PermitAlreadyExistsError(PermitApiDetailedError):
    """
    Object already exists response from the Permit API.
    """


class PermitNotFoundError(PermitApiDetailedError):
    """
    Object not found response from the Permit API.
    """


async def handle_api_error(response: aiohttp.ClientResponse):
    if 200 <= response.status < 400:
        return

    try:
        json = await response.json()
    except aiohttp.ContentTypeError as e:
        text = await response.text()
        raise PermitApiError(response, {"details": text}) from e

    if response.status == 422:
        try:
            validation_content = HTTPValidationError.parse_obj(json)
        except ValidationError as e:
            raise PermitApiError(response, json) from e
        else:
            raise PermitValidationError(response, validation_content, json)

    try:
        content = ErrorDetails.parse_obj(json)
    except ValidationError as e:
        raise PermitApiError(response, json) from e

    if response.status == 409:
        raise PermitAlreadyExistsError(response, content, json)
    elif response.status == 404:
        raise PermitNotFoundError(response, content, json)
    else:
        raise PermitApiDetailedError(response, content, json)


def handle_client_error(func):
    @functools.wraps(func)
    async def wrapped(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except aiohttp.ClientError as err:
            logger.error(f"got client error while sending an http request:\n{err}")
            raise PermitConnectionError(f"{err}", error=err) from err

    return wrapped
