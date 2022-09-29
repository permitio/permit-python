from typing import Any, Dict, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...models.remove_role_permissions import RemoveRolePermissions
from ...models.role_read import RoleRead
from ...types import UNSET, Response, Unset


def _get_kwargs(
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: AuthenticatedClient,
    json_body: RemoveRolePermissions,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/schema/{proj_id}/{env_id}/roles/{role_id}/permissions".format(
        client.base_url, proj_id=proj_id, env_id=env_id, role_id=role_id
    )

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

    json_json_body = json_body.dict()

    return {
        "method": "delete",
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
        "json": json_json_body,
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[HTTPValidationError, RoleRead]]:
    if response.status_code == 200:
        response_200 = RoleRead.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, RoleRead]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: AuthenticatedClient,
    json_body: RemoveRolePermissions,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, RoleRead]]:
    """Remove Permissions From Role

     Remove permissions from role.

    If some of the permissions specified are already unassigned, will skip them.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str): Either the unique id of the role, or the URL-friendly key of the role (i.e:
            the "slug").
        permit_session (Union[Unset, str]):
        json_body (RemoveRolePermissions):  Example: {'permissions': ['document:share']}.

    Returns:
        Response[Union[HTTPValidationError, RoleRead]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        role_id=role_id,
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
    role_id: str,
    *,
    client: AuthenticatedClient,
    json_body: RemoveRolePermissions,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, RoleRead]]:
    """Remove Permissions From Role

     Remove permissions from role.

    If some of the permissions specified are already unassigned, will skip them.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str): Either the unique id of the role, or the URL-friendly key of the role (i.e:
            the "slug").
        permit_session (Union[Unset, str]):
        json_body (RemoveRolePermissions):  Example: {'permissions': ['document:share']}.

    Returns:
        Response[Union[HTTPValidationError, RoleRead]]
    """

    return sync_detailed(
        proj_id=proj_id,
        env_id=env_id,
        role_id=role_id,
        client=client,
        json_body=json_body,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    proj_id: str,
    env_id: str,
    role_id: str,
    *,
    client: AuthenticatedClient,
    json_body: RemoveRolePermissions,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, RoleRead]]:
    """Remove Permissions From Role

     Remove permissions from role.

    If some of the permissions specified are already unassigned, will skip them.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str): Either the unique id of the role, or the URL-friendly key of the role (i.e:
            the "slug").
        permit_session (Union[Unset, str]):
        json_body (RemoveRolePermissions):  Example: {'permissions': ['document:share']}.

    Returns:
        Response[Union[HTTPValidationError, RoleRead]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        role_id=role_id,
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
    role_id: str,
    *,
    client: AuthenticatedClient,
    json_body: RemoveRolePermissions,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, RoleRead]]:
    """Remove Permissions From Role

     Remove permissions from role.

    If some of the permissions specified are already unassigned, will skip them.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        role_id (str): Either the unique id of the role, or the URL-friendly key of the role (i.e:
            the "slug").
        permit_session (Union[Unset, str]):
        json_body (RemoveRolePermissions):  Example: {'permissions': ['document:share']}.

    Returns:
        Response[Union[HTTPValidationError, RoleRead]]
    """

    return (
        await asyncio_detailed(
            proj_id=proj_id,
            env_id=env_id,
            role_id=role_id,
            client=client,
            json_body=json_body,
            permit_session=permit_session,
        )
    ).parsed
