from typing import Any, Dict, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...models.resource_role_create import ResourceRoleCreate
from ...models.resource_role_read import ResourceRoleRead
from ...types import UNSET, Response, Unset


def _get_kwargs(
    proj_id: str,
    env_id: str,
    resource_id: str,
    *,
    client: AuthenticatedClient,
    json_body: ResourceRoleCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/schema/{proj_id}/{env_id}/resources/{resource_id}/roles".format(
        client.base_url, proj_id=proj_id, env_id=env_id, resource_id=resource_id
    )

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
) -> Optional[Union[HTTPValidationError, ResourceRoleRead]]:
    if response.status_code == 200:
        response_200 = ResourceRoleRead.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, ResourceRoleRead]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    proj_id: str,
    env_id: str,
    resource_id: str,
    *,
    client: AuthenticatedClient,
    json_body: ResourceRoleCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, ResourceRoleRead]]:
    """Create Resource Role

     Creates a new role associated with the resource.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (ResourceRoleCreate):  Example: {'key': 'maintainer', 'name': 'Maintainer',
            'description': 'the maintainer role can read from the repo and push changes',
            'permissions': ['push'], 'extends': ['contributor']}.

    Returns:
        Response[Union[HTTPValidationError, ResourceRoleRead]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        resource_id=resource_id,
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
    proj_id: str,
    env_id: str,
    resource_id: str,
    *,
    client: AuthenticatedClient,
    json_body: ResourceRoleCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, ResourceRoleRead]]:
    """Create Resource Role

     Creates a new role associated with the resource.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (ResourceRoleCreate):  Example: {'key': 'maintainer', 'name': 'Maintainer',
            'description': 'the maintainer role can read from the repo and push changes',
            'permissions': ['push'], 'extends': ['contributor']}.

    Returns:
        Response[Union[HTTPValidationError, ResourceRoleRead]]
    """

    return sync_detailed(
        proj_id=proj_id,
        env_id=env_id,
        resource_id=resource_id,
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    proj_id: str,
    env_id: str,
    resource_id: str,
    *,
    client: AuthenticatedClient,
    json_body: ResourceRoleCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, ResourceRoleRead]]:
    """Create Resource Role

     Creates a new role associated with the resource.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (ResourceRoleCreate):  Example: {'key': 'maintainer', 'name': 'Maintainer',
            'description': 'the maintainer role can read from the repo and push changes',
            'permissions': ['push'], 'extends': ['contributor']}.

    Returns:
        Response[Union[HTTPValidationError, ResourceRoleRead]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        resource_id=resource_id,
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    proj_id: str,
    env_id: str,
    resource_id: str,
    *,
    client: AuthenticatedClient,
    json_body: ResourceRoleCreate,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, ResourceRoleRead]]:
    """Create Resource Role

     Creates a new role associated with the resource.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        permit_session (Union[Unset, str]):
        json_body (ResourceRoleCreate):  Example: {'key': 'maintainer', 'name': 'Maintainer',
            'description': 'the maintainer role can read from the repo and push changes',
            'permissions': ['push'], 'extends': ['contributor']}.

    Returns:
        Response[Union[HTTPValidationError, ResourceRoleRead]]
    """

    return (
        await asyncio_detailed(
            proj_id=proj_id,
            env_id=env_id,
            resource_id=resource_id,
            client=client,
            json_body=json_body,
            permit_session=permit_session,
        )
    ).parsed
