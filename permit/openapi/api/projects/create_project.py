from typing import Any, Dict, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...models.project_create import ProjectCreate
from ...models.project_read import ProjectRead
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    client: AuthenticatedClient,
    json_body: ProjectCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/projects".format(client.base_url)

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

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
) -> Optional[Union[HTTPValidationError, ProjectRead]]:
    if response.status_code == 200:
        response_200 = ProjectRead.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, ProjectRead]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    json_body: ProjectCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, ProjectRead]]:
    """Create Project

     Creates a new project under the active organization.

    Args:
        permit_session (Union[Unset, str]):
        json_body (ProjectCreate):

    Returns:
        Response[Union[HTTPValidationError, ProjectRead]]
    """

    kwargs = _get_kwargs(
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
    *,
    client: AuthenticatedClient,
    json_body: ProjectCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, ProjectRead]]:
    """Create Project

     Creates a new project under the active organization.

    Args:
        permit_session (Union[Unset, str]):
        json_body (ProjectCreate):

    Returns:
        Response[Union[HTTPValidationError, ProjectRead]]
    """

    return sync_detailed(
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    json_body: ProjectCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, ProjectRead]]:
    """Create Project

     Creates a new project under the active organization.

    Args:
        permit_session (Union[Unset, str]):
        json_body (ProjectCreate):

    Returns:
        Response[Union[HTTPValidationError, ProjectRead]]
    """

    kwargs = _get_kwargs(
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    json_body: ProjectCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, ProjectRead]]:
    """Create Project

     Creates a new project under the active organization.

    Args:
        permit_session (Union[Unset, str]):
        json_body (ProjectCreate):

    Returns:
        Response[Union[HTTPValidationError, ProjectRead]]
    """

    return (
        await asyncio_detailed(
            client=client,
            json_body=json_body,
            permit_session=permit_session,
        )
    ).parsed
