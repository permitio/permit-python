import functools
import json as json_module
import warnings
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, TypeVar, cast

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy
from typing_extensions import ParamSpec, deprecated

from permit.utils.pydantic_version import PYDANTIC_VERSION
from permit.utils.sdk_logger import sdk_logger

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

        def __init__(self, message: object, *, error: aiohttp.ClientError | None = None) -> None:
            # Every raise site builds its message from response bodies and aiohttp error
            # text, so the key is replaced here, once, rather than at each of them. The
            # class is public, and a message that isn't a string is kept as it is.
            super().__init__(sdk_logger.scrub(message) if isinstance(message, str) else message)
            if error is not None:
                scrub_request_info(error)
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
        scrub_request_info(response)
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


_JsonT = TypeVar("_JsonT")


def _scrubbed(value: _JsonT) -> _JsonT:
    """Return `value`, a decoded JSON body, with every registered API key replaced.

    Strings are scrubbed wherever they are, object keys included.
    """
    if isinstance(value, str):
        return cast("_JsonT", sdk_logger.scrub(value))
    if isinstance(value, list):
        return cast("_JsonT", [_scrubbed(item) for item in value])
    if isinstance(value, dict):
        return cast(
            "_JsonT",
            {_scrubbed(key): _scrubbed(item) for key, item in value.items()},
        )
    return value


def _scrubbed_headers(headers: Mapping[str, str]) -> CIMultiDictProxy[str]:
    return CIMultiDictProxy(
        CIMultiDict((name, sdk_logger.scrub(value)) for name, value in headers.items())
    )


# The attributes, besides `args`, in which aiohttp's errors and the HTTP parser errors
# chained under them keep text a server sent: `message` (ClientResponseError,
# HttpProcessingError), `line` (BadStatusLine), and `_url` and `_description` (InvalidURL
# and its redirect subclasses, whose str() and repr() read `_url`, not `args`).
_TEXT_ATTRIBUTES = ("message", "line", "_url", "_description")


def _chain(error: BaseException) -> list[BaseException]:
    """`error` and every exception chained under it, as a traceback prints them."""
    chain: list[BaseException] = []
    pending: list[BaseException | None] = [error]
    while pending:
        current = pending.pop()
        if current is None or any(current is seen for seen in chain):
            continue
        chain.append(current)
        pending += [current.__cause__, current.__context__]
    return chain


def _scrub_error_text(error: BaseException) -> None:
    attributes = getattr(error, "__dict__", {})
    for name in _TEXT_ATTRIBUTES:
        value = attributes.get(name)
        # `_url` may be a yarl URL: replaced with its scrubbed text only if it holds a key.
        if value is None or not (isinstance(value, str) or name == "_url"):
            continue
        text = str(value)
        if sdk_logger.scrub(text) != text:
            setattr(error, name, sdk_logger.scrub(text))
    if isinstance(attributes.get("headers"), Mapping):
        error.headers = _scrubbed_headers(error.headers)  # type: ignore[attr-defined]
    error.args = tuple(sdk_logger.scrub(arg) if isinstance(arg, str) else arg for arg in error.args)


def scrub_request_info(holder: object) -> None:
    """Replace every client's API key in the request headers and error text `holder` keeps.

    aiohttp keeps the request's headers, `Authorization` included, on a
    `ClientResponse` and a `ClientResponseError` (`request_info`, which the error also
    keeps as `args[0]`), and on the redirect responses in their `history`; their `repr`
    prints them. An aiohttp error's text may also hold text a server sent: a
    `ClientResponseError`'s `message` and the response `headers` it keeps, another
    error's string arguments or URL, and the HTTP parser errors chained under it. The SDK
    puts such objects in the exceptions it raises (`original_error`, `response`, the
    exception's cause), so it scrubs them, and every exception chained under an error,
    first. A `ClientResponse`'s own URL, headers and body, and anything else, are left as
    they are.

    Args:
        holder: An aiohttp response or client error.
    """
    if isinstance(holder, BaseException):
        for error in _chain(holder):
            _scrub_holder(error)
    else:
        _scrub_holder(holder)


def _scrub_holder(holder: object) -> None:
    for redirect in getattr(holder, "history", None) or ():
        if redirect is not holder:
            scrub_request_info(redirect)
    if isinstance(holder, BaseException):
        _scrub_error_text(holder)
    info = getattr(holder, "request_info", None)
    if not isinstance(info, aiohttp.RequestInfo):
        return
    headers = _scrubbed_headers(info.headers)
    if headers == info.headers:
        return
    scrubbed = aiohttp.RequestInfo(info.url, info.method, headers, info.real_url)
    if isinstance(holder, aiohttp.ClientResponse):
        # `request_info` is a read-only property over `_request_info`, cached once read
        # (aiohttp's `reify`): replace both. tests/test_fix_logging.py checks the result.
        holder._request_info = scrubbed  # noqa: SLF001
        cache = getattr(holder, "_cache", None)
        if isinstance(cache, dict) and "request_info" in cache:
            cache["request_info"] = scrubbed
    else:
        holder.request_info = scrubbed  # type: ignore[attr-defined]
        if isinstance(holder, BaseException):
            holder.args = tuple(scrubbed if arg is info else arg for arg in holder.args)


def _scrubbed_loads(text: str) -> Any:  # noqa: ANN401 - any JSON value
    return json_module.loads(sdk_logger.scrub(text))


async def _scrubbed_text(response: aiohttp.ClientResponse) -> str:
    """The body of `response` as text, every registered API key replaced."""
    return sdk_logger.scrub(await response.text(errors="replace"))


async def _error_json(response: aiohttp.ClientResponse) -> Any:  # noqa: ANN401 - any JSON value
    """The decoded JSON body of an error response, every registered API key replaced.

    Raises:
        PermitApiError: When the body is not JSON, whatever its Content-Type says.
    """
    try:
        # The body is scrubbed before it is parsed too, so a decode error's `doc` never
        # holds the key.
        return _scrubbed(await response.json(loads=_scrubbed_loads))
    except aiohttp.ContentTypeError as e:
        scrub_request_info(e)
        raise PermitApiError(response, {"details": await _scrubbed_text(response)}) from e
    except ValueError:
        # Labelled JSON but not JSON, such as a proxy's error page or a truncated body.
        # A UnicodeDecodeError keeps the raw bytes, so the decode error isn't chained:
        # raised after this block, it isn't the new exception's context either.
        error = PermitApiError(response, {"details": await _scrubbed_text(response)})
    raise error


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

    json = await _error_json(response)

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
            sdk_logger.error(f"got client error while sending an http request:\n{err}")
            msg = f"{err}"
            raise PermitConnectionError(msg, error=err) from err

    return wrapped
