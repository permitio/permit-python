import functools
import warnings
from collections.abc import Awaitable, Callable, Coroutine
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, TypeVar

import aiohttp
from loguru import logger
from typing_extensions import ParamSpec, deprecated

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import ValidationError
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import ValidationError
else:
    from pydantic.v1 import ValidationError

from permit.api.models import ErrorDetails, HTTPValidationError

DEFAULT_SUPPORT_LINK = "https://permit-io.slack.com/ssb/redirect"

P = ParamSpec("P")
R = TypeVar("R")


class PermitError(Exception):
    """Permit base exception."""


@deprecated("Use PermitError instead")
class PermitException(PermitError):  # noqa: N818 - public name, kept for existing callers
    """Permit base exception (deprecated, use PermitError instead)."""


# Subclassing a `@deprecated` class warns (typing_extensions hooks `__init_subclass__`).
# This subclass is the SDK's own, so the warning is silenced here: importing the SDK
# stays warning-free, while code that subclasses or raises `PermitException` still warns.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)

    class PermitConnectionError(PermitException):  # type: ignore[deprecated] # kept, see docstring
        """Permit connection exception.

        Note: this deliberately still inherits from the deprecated `PermitException`
        rather than from `PermitError`. Re-parenting it looks like tidying, but it
        silently breaks every consumer whose handler is `except PermitException` --
        a connection blip would stop being caught and become an unhandled crash.
        That is a breaking change worth making, but it belongs in a major version
        with a changelog entry, not in a dependency-security patch.
        """

        def __init__(self, message: str, *, error: aiohttp.ClientError | None = None) -> None:
            super().__init__(message)
            self.original_error = error


class PermitContextError(PermitError):
    """An API method was called without the context it needs.

    The context tells the SDK in which environment, project or organization an
    API call is being made.

    Some of the input for the API method is provided via the SDK context.
    If the context is missing some data required for a method - the api call will fail.
    """


class PermitContextChangeError(PermitError):
    """The SDK context was set to an object the current API key cannot access.

    API calls made in such a context would fail with 401, so the SDK refuses to
    switch to it and raises this exception instead.
    """


class PermitApiError(PermitError):
    """Wraps an error HTTP Response that occurred during a Permit REST API request."""

    def __init__(
        self,
        response: aiohttp.ClientResponse,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._response = response
        self._body = body

    def _get_message(self) -> str:
        return f"{self.status_code} API Error: {self.details}"

    def __str__(self) -> str:
        return self._get_message()

    @property
    def message(self) -> str:
        """The human-readable error message, as `str(error)` renders it."""
        return self._get_message()

    @property
    def response(self) -> aiohttp.ClientResponse:
        """Get the HTTP response that returned an error status code.

        Returns:
            The HTTP response object.
        """
        return self._response

    @property
    def details(self) -> dict[str, Any] | None:
        """Get the HTTP response JSON body. Contains details about the error.

        Returns:
            The HTTP response json. If no content will return None.
        """
        return self._body

    @property
    def request_url(self) -> str:
        """Get the HTTP request URL that caused the error code.

        Returns:
            The HTTP request url
        """
        return str(self._response.url)

    @property
    def status_code(self) -> int:
        """Get the HTTP response status code.

        Returns:
            The status code returned.
        """
        return self._response.status

    @property
    def content_type(self) -> str | None:
        """Get the HTTP content type header of the error response.

        Returns:
            The value of the HTTP Response Content-type header, or None
        """
        return self._response.headers.get("content-type")


class PermitValidationError(PermitApiError):
    """Validation error response from the Permit API."""

    def __init__(
        self, response: aiohttp.ClientResponse, content: HTTPValidationError, body: dict[str, Any]
    ) -> None:
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
        """The parsed validation error body: one entry per invalid input."""
        return self._content


class PermitApiDetailedError(PermitApiError):
    """Detailed error response from the Permit API."""

    def __init__(
        self, response: aiohttp.ClientResponse, content: ErrorDetails, body: dict[str, Any]
    ) -> None:
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
        """The parsed error body."""
        return self._content

    @property
    def id(self) -> str:
        """The request ID, for reference when contacting Permit support."""
        return self.content.id

    @property
    def code(self) -> str:
        """The machine-readable error code."""
        return self.content.error_code.value

    @property
    def title(self) -> str:
        """A short summary of the error."""
        return self.content.title

    @property
    def explanation(self) -> str:
        """The API's explanation of the error, or a placeholder when it gave none."""
        return self.content.message or "No further explanation provided"

    @property
    def support_link(self) -> str:
        """Where to get help with this error."""
        return str(self.content.support_link or DEFAULT_SUPPORT_LINK)

    @property
    def additional_info(self) -> Any:  # noqa: ANN401 - arbitrary JSON sent by the API
        """Extra error-specific data from the API, if any."""
        return self.content.additional_info


class PermitAlreadyExistsError(PermitApiDetailedError):
    """Object already exists response from the Permit API."""


class PermitNotFoundError(PermitApiDetailedError):
    """Object not found response from the Permit API."""


async def handle_api_error(response: aiohttp.ClientResponse) -> None:
    """Raise the matching SDK exception if `response` has a non-2xx status.

    Args:
        response: The Permit REST API response to inspect.

    Raises:
        PermitValidationError: On 422 with a validation error body.
        PermitAlreadyExistsError: On 409.
        PermitNotFoundError: On 404.
        PermitApiDetailedError: On any other error status with a detailed error body.
        PermitApiError: When the error body is not JSON or has an unexpected shape.
    """
    if HTTPStatus.OK <= response.status < HTTPStatus.MULTIPLE_CHOICES:
        return

    try:
        json = await response.json()
    except aiohttp.ContentTypeError as e:
        text = await response.text()
        raise PermitApiError(response, {"details": text}) from e

    if response.status == HTTPStatus.UNPROCESSABLE_ENTITY:
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

    if response.status == HTTPStatus.CONFLICT:
        raise PermitAlreadyExistsError(response, content, json)
    if response.status == HTTPStatus.NOT_FOUND:
        raise PermitNotFoundError(response, content, json)
    raise PermitApiDetailedError(response, content, json)


def handle_client_error(
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Re-raise aiohttp client errors from `func` as `PermitConnectionError`.

    Args:
        func: The coroutine function sending the HTTP request.

    Returns:
        A coroutine function with the same signature.
    """

    @functools.wraps(func)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except aiohttp.ClientError as err:
            logger.error(f"got client error while sending an http request:\n{err}")
            msg = f"{err}"
            raise PermitConnectionError(msg, error=err) from err

    return wrapped
