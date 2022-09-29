from typing import Any, Dict, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...models.organization_read import OrganizationRead
from ...models.organization_update import OrganizationUpdate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    org_id: str,
    *,
    client: AuthenticatedClient,
    json_body: OrganizationUpdate,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/orgs/{org_id}".format(client.base_url, org_id=org_id)

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

    json_json_body = json_body.dict()

    return {
        "method": "patch",
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
        "json": json_json_body,
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[HTTPValidationError, OrganizationRead]]:
    if response.status_code == 200:
        response_200 = OrganizationRead.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, OrganizationRead]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    org_id: str,
    *,
    client: AuthenticatedClient,
    json_body: OrganizationUpdate,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, OrganizationRead]]:
    """Update Organization

     Updates the organization's profile.

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (OrganizationUpdate):

    Returns:
        Response[Union[HTTPValidationError, OrganizationRead]]
    """

    kwargs = _get_kwargs(
        org_id=org_id,
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    )

    response = httpx.request(
        verify=client.verify_ssl,
        **kwargs,
    )

    return _build_response(response=response)


def sync(
    org_id: str,
    *,
    client: AuthenticatedClient,
    json_body: OrganizationUpdate,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, OrganizationRead]]:
    """Update Organization

     Updates the organization's profile.

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (OrganizationUpdate):

    Returns:
        Response[Union[HTTPValidationError, OrganizationRead]]
    """

    return sync_detailed(
        org_id=org_id,
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    org_id: str,
    *,
    client: AuthenticatedClient,
    json_body: OrganizationUpdate,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, OrganizationRead]]:
    """Update Organization

     Updates the organization's profile.

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (OrganizationUpdate):

    Returns:
        Response[Union[HTTPValidationError, OrganizationRead]]
    """

    kwargs = _get_kwargs(
        org_id=org_id,
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    org_id: str,
    *,
    client: AuthenticatedClient,
    json_body: OrganizationUpdate,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, OrganizationRead]]:
    """Update Organization

     Updates the organization's profile.

    Args:
        org_id (str): Either the unique id of the organization, or the URL-friendly key of the
            organization (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (OrganizationUpdate):

    Returns:
        Response[Union[HTTPValidationError, OrganizationRead]]
    """

    return (
        await asyncio_detailed(
            org_id=org_id,
            client=client,
            json_body=json_body,
            permit_session=permit_session,
        )
    ).parsed
