from typing import Any, Dict, Optional, Union

import httpx

from permit.openapi.client import AuthenticatedClient
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead
from permit.openapi.models.http_validation_error import HTTPValidationError
from permit.openapi.types import Response


def _get_kwargs(
    *,
    client: AuthenticatedClient,
) -> Dict[str, Any]:
    url = "{}/v2/api-key/scope".format(client.base_url)

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    return {
        "method": "get",
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[APIKeyScopeRead, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = APIKeyScopeRead.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[APIKeyScopeRead, HTTPValidationError]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[Union[APIKeyScopeRead, HTTPValidationError]]:
    """Get Api Key Scope

    Returns:
        Response[Union[APIKeyScopeRead, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        client=client,
    )

    response = httpx.request(
        verify=client.verify_ssl,
        **kwargs,
    )

    return _build_response(response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> Optional[Union[APIKeyScopeRead, HTTPValidationError]]:
    """Get Api Key Scope

    Returns:
        Response[Union[APIKeyScopeRead, HTTPValidationError]]
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[Union[APIKeyScopeRead, HTTPValidationError]]:
    """Get Api Key Scope

    Returns:
        Response[Union[APIKeyScopeRead, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        client=client,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> Optional[Union[APIKeyScopeRead, HTTPValidationError]]:
    """Get Api Key Scope

    Returns:
        Response[Union[APIKeyScopeRead, HTTPValidationError]]
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
