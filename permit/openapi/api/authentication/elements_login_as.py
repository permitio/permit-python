from http import HTTPStatus
from typing import Any, Dict, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...models.user_login_request import UserLoginRequest
from ...models.user_login_response import UserLoginResponse
from ...types import Response


def _get_kwargs(
    *,
    client: AuthenticatedClient,
    json_body: UserLoginRequest,
) -> Dict[str, Any]:
    url = "{}/v2/auth/elements_login_as".format(client.base_url)
    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()
    json_json_body = json_body.dict()
    return {
        "method": "post",
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
        "json": json_json_body,
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[HTTPValidationError, UserLoginResponse]]:
    if response.status_code == HTTPStatus.OK:
        response_200 = UserLoginResponse(**response.json())
        return response_200
    if response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
        response_422 = HTTPValidationError(**response.json())
        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, UserLoginResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    json_body: UserLoginRequest,
) -> Response[Union[HTTPValidationError, UserLoginResponse]]:
    """Generate Embed Token For User

    Args:
        json_body (UserLoginRequest):

    Returns:
        Response[Union[HTTPValidationError, UserLoginResponse]]
    """
    kwargs = _get_kwargs(
        client=client,
        json_body=json_body,
    )
    response = httpx.request(
        verify=client.verify_ssl,
        **kwargs,
    )
    return _build_response(response=response)


def sync(
    *,
    client: AuthenticatedClient,
    json_body: UserLoginRequest,
) -> Optional[Union[HTTPValidationError, UserLoginResponse]]:
    """Generate Embed Token For User

    Args:
        json_body (UserLoginRequest):

    Returns:
        Response[Union[HTTPValidationError, UserLoginResponse]]
    """
    return sync_detailed(
        client=client,
        json_body=json_body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    json_body: UserLoginRequest,
) -> Response[Union[HTTPValidationError, UserLoginResponse]]:
    """Generate Embed Token For User

    Args:
        json_body (UserLoginRequest):

    Returns:
        Response[Union[HTTPValidationError, UserLoginResponse]]
    """
    kwargs = _get_kwargs(
        client=client,
        json_body=json_body,
    )
    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)
    return _build_response(response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    json_body: UserLoginRequest,
) -> Optional[Union[HTTPValidationError, UserLoginResponse]]:
    """Generate Embed Token For User

    Args:
        json_body (UserLoginRequest):

    Returns:
        Response[Union[HTTPValidationError, UserLoginResponse]]
    """

    return (
        await asyncio_detailed(
            client=client,
            json_body=json_body,
        )
    ).parsed
