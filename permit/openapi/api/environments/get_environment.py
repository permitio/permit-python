from typing import Any, Dict, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models.environment_read import EnvironmentRead
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/projects/{proj_id}/envs/{env_id}".format(
        client.base_url, proj_id=proj_id, env_id=env_id
    )

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

    return {
        "method": "get",
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[EnvironmentRead, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = EnvironmentRead.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[EnvironmentRead, HTTPValidationError]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[EnvironmentRead, HTTPValidationError]]:
    """Get Environment

     Gets a single environment matching the given env_id, if such environment exists.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[EnvironmentRead, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        permit_session=permit_session,
    )

    response = httpx.request(
        verify=client.verify_ssl,
        **kwargs,
    )

    return _build_response(response=response)


def sync(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[EnvironmentRead, HTTPValidationError]]:
    """Get Environment

     Gets a single environment matching the given env_id, if such environment exists.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[EnvironmentRead, HTTPValidationError]]
    """

    return sync_detailed(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[EnvironmentRead, HTTPValidationError]]:
    """Get Environment

     Gets a single environment matching the given env_id, if such environment exists.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[EnvironmentRead, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        permit_session=permit_session,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[EnvironmentRead, HTTPValidationError]]:
    """Get Environment

     Gets a single environment matching the given env_id, if such environment exists.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[EnvironmentRead, HTTPValidationError]]
    """

    return (
        await asyncio_detailed(
            proj_id=proj_id,
            env_id=env_id,
            client=client,
            permit_session=permit_session,
        )
    ).parsed
