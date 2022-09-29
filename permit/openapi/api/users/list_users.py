from typing import Any, Dict, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models import PaginatedResultUserRead
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    search: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/facts/{proj_id}/{env_id}/users".format(
        client.base_url, proj_id=proj_id, env_id=env_id
    )

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

    params: Dict[str, Any] = {}
    params["search"] = search

    params["page"] = page

    params["per_page"] = per_page

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    return {
        "method": "get",
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
        "params": params,
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[HTTPValidationError, PaginatedResultUserRead]]:
    if response.status_code == 200:
        response_200 = PaginatedResultUserRead.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, PaginatedResultUserRead]]:
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
    search: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, PaginatedResultUserRead]]:
    """List Users

     Lists all the users defined within an environment.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        search (Union[Unset, None, str]): Text search for the email field
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, PaginatedResultUserRead]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        search=search,
        page=page,
        per_page=per_page,
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
    search: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, PaginatedResultUserRead]]:
    """List Users

     Lists all the users defined within an environment.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        search (Union[Unset, None, str]): Text search for the email field
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, PaginatedResultUserRead]]
    """

    return sync_detailed(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        search=search,
        page=page,
        per_page=per_page,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    search: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, PaginatedResultUserRead]]:
    """List Users

     Lists all the users defined within an environment.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        search (Union[Unset, None, str]): Text search for the email field
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, PaginatedResultUserRead]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        search=search,
        page=page,
        per_page=per_page,
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
    search: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, PaginatedResultUserRead]]:
    """List Users

     Lists all the users defined within an environment.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        search (Union[Unset, None, str]): Text search for the email field
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, PaginatedResultUserRead]]
    """

    return (
        await asyncio_detailed(
            proj_id=proj_id,
            env_id=env_id,
            client=client,
            search=search,
            page=page,
            per_page=per_page,
            permit_session=permit_session,
        )
    ).parsed
