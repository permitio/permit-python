import functools
import json as json_module
import sys
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

        def __init__(
            self,
            message: object,
            *,
            error: aiohttp.ClientError | None = None,
            handled: BaseException | None = None,
        ) -> None:
            # Every raise site builds its message from response bodies and aiohttp error
            # text, so the key is replaced here, once, rather than at each of them. The
            # class is public, and a message that isn't a string is kept as it is.
            # `handled` is the exception the application was handling when it called the
            # SDK (see `scrub_request_info`).
            super().__init__(sdk_logger.scrub(message) if isinstance(message, str) else message)
            if error is not None and not scrub_request_info(error, handled=handled):
                # Fail closed: an error the key could not be removed from is not attached.
                # The SDK raises this exception `from original_error`, so it is not the
                # cause either.
                error = aiohttp.ClientError(
                    f"{type(error).__name__}, not attached: the API key could not be "
                    "removed from it"
                )
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
        # The result isn't needed: on a `ClientResponse` the scrub writes only
        # `_request_info` and its cache, a plain attribute and a dict, so it can't fail.
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


# The packages whose code an SDK request runs through: aiohttp, the libraries it raises
# errors from, asyncio, and the SDK itself.
_REQUEST_PACKAGES = frozenset(
    {
        "aiohappyeyeballs",
        "aiohttp",
        "asyncio",
        "concurrent",
        "multidict",
        "permit",
        "propcache",
        "selectors",
        "socket",
        "ssl",
        "yarl",
    }
)


def _raised_in_the_request(error: BaseException) -> bool:
    """Whether `error` was raised and caught within the SDK's request.

    That is, whether every frame of its traceback is in one of `_REQUEST_PACKAGES`. An
    exception the application raised or caught has a frame of the application's, so the
    SDK doesn't change it. So does an error raised in a library missing from the list,
    which `_scrub_chain` then checks for a key instead.
    """
    frame = error.__traceback__
    if frame is None:
        return False
    while frame is not None:
        module = frame.tb_frame.f_globals.get("__name__")
        if not isinstance(module, str) or module.partition(".")[0] not in _REQUEST_PACKAGES:
            return False
        frame = frame.tb_next
    return True


def _chained(error: BaseException) -> list[BaseException | None]:
    return [error.__cause__, error.__context__]


def _chain(
    error: BaseException, handled: BaseException | None
) -> tuple[list[BaseException], list[BaseException]]:
    """The exceptions reachable from `error` through `__cause__` and `__context__`.

    Returns them in two lists: those to scrub, which are `error`, the one the SDK caught,
    and those under it raised in the request; and the others under it, which are left as
    they are and which the walk doesn't go past. `handled` and what is chained under it
    are in neither: they are the application's.
    """
    scrub: list[BaseException] = [error]
    left: list[BaseException] = []
    seen: set[int] = {id(error)}
    if handled is not None:
        seen.add(id(handled))
    pending = _chained(error)
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if _raised_in_the_request(current):
            scrub.append(current)
            pending += _chained(current)
        else:
            left.append(current)
    return scrub, left


# Text a builtin exception keeps in fields of its own, outside `__dict__` and `args`: a
# `UnicodeError`'s `object`, an `OSError`'s file names and `strerror`, a `SyntaxError`'s
# `text`.
_BUILTIN_TEXT_FIELDS = ("object", "filename", "filename2", "strerror", "text")


def _holds_key(error: BaseException) -> bool:
    """Whether the text `error` keeps or shows holds a registered key."""
    shown = [str(error), repr(error.args), repr(getattr(error, "__dict__", {}))]
    shown += [repr(getattr(error, name)) for name in _BUILTIN_TEXT_FIELDS if hasattr(error, name)]
    return any(sdk_logger.scrub(text) != text for text in shown)


def _below(errors: list[BaseException], handled: BaseException | None) -> list[BaseException]:
    """`errors` and everything chained under them, `handled` and what is under it apart."""
    found: list[BaseException] = []
    seen: set[int] = set() if handled is None else {id(handled)}
    pending: list[BaseException | None] = list(errors)
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        found.append(current)
        pending += _chained(current)
    return found


def _scrubbed_value(value: object) -> object:
    """`value` with every registered key replaced, if it is text that can hold one.

    That is a string, bytes, or a yarl URL, which comes back as a string when it holds a
    key. Any other value, such as a parsed HTTP message, comes back as it is, and so does
    a value without a key: the very same object.
    """
    scrubbed: object = value
    if isinstance(value, str):
        scrubbed = sdk_logger.scrub(value)
    elif isinstance(value, bytes):
        scrubbed = sdk_logger.scrub_bytes(value)
    elif isinstance(value, bytearray):
        scrubbed = bytearray(sdk_logger.scrub_bytes(bytes(value)))
    elif type(value).__module__.partition(".")[0] == "yarl":
        text = str(value)
        scrubbed = sdk_logger.scrub(text)
        if scrubbed == text:
            return value
    return value if scrubbed == value else scrubbed


def _replace(holder: object, name: str, value: object) -> bool:
    """Set `holder.name` to `value`; False, never an exception, if it can't be set."""
    try:
        setattr(holder, name, value)
    except Exception:  # noqa: BLE001 - any failure is reported, never raised
        return False
    return True


def _scrub_error_text(error: BaseException) -> bool:
    """Replace the key in the text `error` keeps; False if some of it can't be replaced.

    The text is its arguments and its attributes: a `message`, a `line`, an
    `InvalidURL`'s `_url`, and the like. Only values that hold a key are written.
    """
    scrubbed = True
    for name, value in list(getattr(error, "__dict__", {}).items()):
        if name == "headers" and isinstance(value, Mapping):
            items = [(key, item, _scrubbed_value(item)) for key, item in value.items()]
            if any(new is not item for _, item, new in items):
                headers = CIMultiDictProxy(CIMultiDict((key, new) for key, _, new in items))
                scrubbed &= _replace(error, name, headers)
            continue
        new_value = _scrubbed_value(value)
        if new_value is not value:
            scrubbed &= _replace(error, name, new_value)
    args = tuple(_scrubbed_value(arg) for arg in error.args)
    if any(new is not arg for new, arg in zip(args, error.args, strict=True)):
        scrubbed &= _replace(error, "args", args)
    return scrubbed


def scrub_request_info(holder: object, *, handled: BaseException | None = None) -> bool:
    """Replace every client's API key in the request headers and error text `holder` keeps.

    aiohttp keeps the request's headers, `Authorization` included, on a
    `ClientResponse` and a `ClientResponseError` (`request_info`, which the error also
    keeps as `args[0]`), and on the redirect responses in their `history`; their `repr`
    prints them. An aiohttp error's text may also hold text a server sent: its string and
    bytes arguments and attributes (a `ClientResponseError`'s `message`, an `InvalidURL`'s
    URL), the response `headers` it keeps, and the same in the HTTP parser and URL errors
    chained under it. The SDK puts such objects in the exceptions it raises
    (`original_error`, `response`, the exception's cause), so it scrubs them first.

    Only values that hold a key are changed, in the error itself and in what was raised
    within the request under it (see `_raised_in_the_request`). `handled`, the exception
    the application was handling when it called the SDK, which aiohttp's errors keep as
    their `__context__`, is left as it is, and so is everything chained under it. So are
    a `ClientResponse`'s own URL, headers and body, and values that aren't text, such as a
    parsed HTTP message.

    Args:
        holder: An aiohttp response or client error.
        handled: The exception the application was handling when it called the SDK.

    Returns:
        False if the key may still be in what `holder` keeps: a value that holds it could
        not be replaced, or an exception left as it is holds it. It never raises.
    """
    try:
        if isinstance(holder, BaseException):
            return _scrub_chain(holder, handled)
        return _scrub_holder(holder)
    except Exception:  # noqa: BLE001 - a scrub that fails is reported, never raised
        return False


def _scrub_chain(error: BaseException, handled: BaseException | None) -> bool:
    scrubbed = True
    to_scrub, left = _chain(error, handled)
    # Every one is scrubbed, even after one that could not be.
    for chained in to_scrub:
        scrubbed &= _scrub_holder(chained)
    # The key can still be where no write reaches: in text kept outside `__dict__` (a
    # `UnicodeError`'s `object`), or in an exception left as it is, or under one.
    return scrubbed and not any(_holds_key(shown) for shown in [*to_scrub, *_below(left, handled)])


def _scrub_holder(holder: object) -> bool:
    scrubbed = True
    for redirect in getattr(holder, "history", None) or ():
        if redirect is not holder:
            scrubbed &= scrub_request_info(redirect)
    if isinstance(holder, BaseException):
        scrubbed &= _scrub_error_text(holder)
    info = getattr(holder, "request_info", None)
    if not isinstance(info, aiohttp.RequestInfo):
        return scrubbed
    headers = _scrubbed_headers(info.headers)
    if headers == info.headers:
        return scrubbed
    replacement = aiohttp.RequestInfo(info.url, info.method, headers, info.real_url)
    if isinstance(holder, aiohttp.ClientResponse):
        # `request_info` is a read-only property over `_request_info`, cached once read
        # (aiohttp's `reify`): replace both. tests/test_fix_logging.py checks the result.
        scrubbed &= _replace(holder, "_request_info", replacement)
        cache = getattr(holder, "_cache", None)
        if isinstance(cache, dict) and "request_info" in cache:
            cache["request_info"] = replacement
        return scrubbed
    scrubbed &= _replace(holder, "request_info", replacement)
    if isinstance(holder, BaseException):
        args = tuple(replacement if arg is info else arg for arg in holder.args)
        scrubbed &= _replace(holder, "args", args)
    return scrubbed


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
    handled = sys.exc_info()[1]
    cause: aiohttp.ContentTypeError | None = None
    try:
        # The body is scrubbed before it is parsed too, so a decode error's `doc` never
        # holds the key.
        return _scrubbed(await response.json(loads=_scrubbed_loads))
    except aiohttp.ContentTypeError as e:
        # Not chained to an error the key could not be removed from.
        if scrub_request_info(e, handled=handled):
            cause = e
    except ValueError:
        # Labelled JSON but not JSON, such as a proxy's error page or a truncated body.
        # A UnicodeDecodeError keeps the raw bytes, so the decode error isn't chained.
        pass
    # Raised after the `except` blocks, so the error caught there isn't the new
    # exception's context.
    error = PermitApiError(response, {"details": await _scrubbed_text(response)})
    if cause is None:
        raise error
    raise error from cause


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
        handled = sys.exc_info()[1]
        try:
            return await func(*args, **kwargs)
        except aiohttp.ClientError as err:
            sdk_logger.error(f"got client error while sending an http request:\n{err}")
            msg = f"{err}"
            error = PermitConnectionError(msg, error=err, handled=handled)
        # Raised after the `except` block, so `err` isn't its context when it isn't
        # attached.
        raise error from error.original_error

    return wrapped
