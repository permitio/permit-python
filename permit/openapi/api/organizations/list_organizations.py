from typing import Any, Dict, List, Optional, Union

import httpx

from ..utils import parse_response
from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...models.organization_read import OrganizationRead
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    client: AuthenticatedClient,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/orgs".format(client.base_url)

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

    params: Dict[str, Any] = {}
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
) -> Optional[Union[HTTPValidationError, List[OrganizationRead]]]:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = OrganizationRead.parse_obj(response_200_item_data)

            response_200.append(response_200_item)

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, List[OrganizationRead]]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=parse_response(response=response, model=List[OrganizationRead]),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, List[OrganizationRead]]]:
    """List Organizations

     Lists all the organizations that can be accessed by the
    authenticated actor (i.e: human team member or api key).

    Args:
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[OrganizationRead]]]
    """

    kwargs = _get_kwargs(
        client=client,
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
    *,
    client: AuthenticatedClient,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, List[OrganizationRead]]]:
    """List Organizations

     Lists all the organizations that can be accessed by the
    authenticated actor (i.e: human team member or api key).

    Args:
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[OrganizationRead]]]
    """

    return sync_detailed(
        client=client,
        page=page,
        per_page=per_page,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, List[OrganizationRead]]]:
    """List Organizations

     Lists all the organizations that can be accessed by the
    authenticated actor (i.e: human team member or api key).

    Args:
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[OrganizationRead]]]
    """

    kwargs = _get_kwargs(
        client=client,
        page=page,
        per_page=per_page,
        permit_session=permit_session,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, List[OrganizationRead]]]:
    """List Organizations

     Lists all the organizations that can be accessed by the
    authenticated actor (i.e: human team member or api key).

    Args:
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[OrganizationRead]]]
    """

    return (
        await asyncio_detailed(
            client=client,
            page=page,
            per_page=per_page,
            permit_session=permit_session,
        )
    ).parsed
