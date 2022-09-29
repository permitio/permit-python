from typing import Any, Dict, Optional, Union

import httpx

from ...client import Client
from ...models.http_validation_error import HTTPValidationError
from ...models.role_data import RoleData
from ...types import Response


def _get_kwargs(
    org_id: str,
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: Client,
) -> Dict[str, Any]:
    url = "{}/v2/internal/opal_data/{org_id}/{proj_id}/{env_id}/roles/{role_id}".format(
        client.base_url, org_id=org_id, proj_id=proj_id, env_id=env_id, role_id=role_id
    )

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
) -> Optional[Union[HTTPValidationError, RoleData]]:
    if response.status_code == 200:
        response_200 = RoleData.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, RoleData]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    org_id: str,
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: Client,
) -> Response[Union[HTTPValidationError, RoleData]]:
    """Get Data For Role

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str):

    Returns:
        Response[Union[HTTPValidationError, RoleData]]
    """

    kwargs = _get_kwargs(
        org_id=org_id,
        proj_id=proj_id,
        env_id=env_id,
        role_id=role_id,
        client=client,
    )

    response = httpx.request(
        verify=client.verify_ssl,
        **kwargs,
    )

    return _build_response(response=response)


def sync(
    org_id: str,
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: Client,
) -> Optional[Union[HTTPValidationError, RoleData]]:
    """Get Data For Role

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str):

    Returns:
        Response[Union[HTTPValidationError, RoleData]]
    """

    return sync_detailed(
        org_id=org_id,
        proj_id=proj_id,
        env_id=env_id,
        role_id=role_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    org_id: str,
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: Client,
) -> Response[Union[HTTPValidationError, RoleData]]:
    """Get Data For Role

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str):

    Returns:
        Response[Union[HTTPValidationError, RoleData]]
    """

    kwargs = _get_kwargs(
        org_id=org_id,
        proj_id=proj_id,
        env_id=env_id,
        role_id=role_id,
        client=client,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    org_id: str,
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: Client,
) -> Optional[Union[HTTPValidationError, RoleData]]:
    """Get Data For Role

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str):

    Returns:
        Response[Union[HTTPValidationError, RoleData]]
    """

    return (
        await asyncio_detailed(
            org_id=org_id,
            proj_id=proj_id,
            env_id=env_id,
            role_id=role_id,
            client=client,
        )
    ).parsed
