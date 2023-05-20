import functools
from typing import Optional
import aiohttp
from loguru import logger


class PermitException(Exception):
    """Permit base exception"""


class PermitConnectionError(PermitException):
    """Permit connection exception"""
    def __init__(self, message: str, *, error: Optional[aiohttp.ClientError] = None):
        super().__init__(message)
        self.original_error = error


class PermitContextError(Exception):
    """
    The `PermitContextError` class represents an error that occurs when an API method
    is called with either insufficient level of API key authorization or trying to call
    an API method that requires a lower level of API key authorization in order to extract
    implicit context (i.e: most API Methods expects an Environment-level API key so the
    environment could be implicitly inferred from the API key itself).
    """
    pass


class PermitApiError(Exception):
    """
    Wraps an error HTTP Response that occured during a Permit REST API request.
    """

    def __init__(self, message: str, response: aiohttp.ClientResponse):
        super().__init__(message)
        self._response = response
    
    @property
    def response(self) -> aiohttp.ClientResponse:
        """
        Get the HTTP response that returned an error status code

        Returns:
            The HTTP response object.
        """
        return self._response
    
    @property
    def status_code(self) -> int:
        """
        Get the HTTP response status code

        Returns:
            The status code returned.
        """
        return self._response.status


def handle_api_error(response: aiohttp.ClientResponse):
    if response.status < 200 or response.status >= 400:
        raise PermitApiError("API error", response)


def handle_client_error(func):
    @functools.wraps(func)
    async def wrapped(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except aiohttp.ClientError as err:
            logger.error(
                "got client error while sending an http request:\n{}".format(err)
            )
            raise PermitConnectionError(f"Permit SDK got error: {err}", err)
    return wrapped