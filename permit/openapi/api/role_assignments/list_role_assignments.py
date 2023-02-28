from typing import Any, Dict, List, Optional, Union

import httpx

from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...models.role_assignment_read import RoleAssignmentRead
from ...types import UNSET, Response, Unset
from ..utils import parse_response


def _get_kwargs(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    user: Union[Unset, None, str] = UNSET,
    role: Union[Unset, None, str] = UNSET,
    tenant: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/facts/{proj_id}/{env_id}/role_assignments".format(
        client.base_url, proj_id=proj_id, env_id=env_id
    )

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

    params: Dict[str, Any] = {}
    params["user"] = user

    params["role"] = role

    params["tenant"] = tenant

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
) -> Optional[Union[HTTPValidationError, List[RoleAssignmentRead]]]:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = RoleAssignmentRead.parse_obj(response_200_item_data)

            response_200.append(response_200_item)

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[HTTPValidationError, List[RoleAssignmentRead]]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=parse_response(response=response, model=List[RoleAssignmentRead]),
    )


def sync_detailed(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    user: Union[Unset, None, str] = UNSET,
    role: Union[Unset, None, str] = UNSET,
    tenant: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, List[RoleAssignmentRead]]]:
    """List Role Assignments

     Lists the role assignments defined within an environment.

    - If the `user` filter is present, will only return the role assignments of that user.
    - If the `tenant` filter is present, will only return the role assignments in that tenant.
    - If the `role` filter is present, will only return role assignments that are granting that role.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        user (Union[Unset, None, str]): optional user filter, will only return role assignments
            granted to this user.
        role (Union[Unset, None, str]): optional role filter, will only return role assignments
            granting this role.
        tenant (Union[Unset, None, str]): optional tenant filter, will only return role
            assignments granted in that tenant.
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[RoleAssignmentRead]]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        user=user,
        role=role,
        tenant=tenant,
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
    user: Union[Unset, None, str] = UNSET,
    role: Union[Unset, None, str] = UNSET,
    tenant: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, List[RoleAssignmentRead]]]:
    """List Role Assignments

     Lists the role assignments defined within an environment.

    - If the `user` filter is present, will only return the role assignments of that user.
    - If the `tenant` filter is present, will only return the role assignments in that tenant.
    - If the `role` filter is present, will only return role assignments that are granting that role.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        user (Union[Unset, None, str]): optional user filter, will only return role assignments
            granted to this user.
        role (Union[Unset, None, str]): optional role filter, will only return role assignments
            granting this role.
        tenant (Union[Unset, None, str]): optional tenant filter, will only return role
            assignments granted in that tenant.
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[RoleAssignmentRead]]]
    """

    return sync_detailed(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        user=user,
        role=role,
        tenant=tenant,
        page=page,
        per_page=per_page,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    proj_id: str,
    env_id: str,
    *,
    client: AuthenticatedClient,
    user: Union[Unset, None, str] = UNSET,
    role: Union[Unset, None, str] = UNSET,
    tenant: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, List[RoleAssignmentRead]]]:
    """List Role Assignments

     Lists the role assignments defined within an environment.

    - If the `user` filter is present, will only return the role assignments of that user.
    - If the `tenant` filter is present, will only return the role assignments in that tenant.
    - If the `role` filter is present, will only return role assignments that are granting that role.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        user (Union[Unset, None, str]): optional user filter, will only return role assignments
            granted to this user.
        role (Union[Unset, None, str]): optional role filter, will only return role assignments
            granting this role.
        tenant (Union[Unset, None, str]): optional tenant filter, will only return role
            assignments granted in that tenant.
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[RoleAssignmentRead]]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        client=client,
        user=user,
        role=role,
        tenant=tenant,
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
    user: Union[Unset, None, str] = UNSET,
    role: Union[Unset, None, str] = UNSET,
    tenant: Union[Unset, None, str] = UNSET,
    page: Union[Unset, None, int] = 1,
    per_page: Union[Unset, None, int] = 30,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, List[RoleAssignmentRead]]]:
    """List Role Assignments

     Lists the role assignments defined within an environment.

    - If the `user` filter is present, will only return the role assignments of that user.
    - If the `tenant` filter is present, will only return the role assignments in that tenant.
    - If the `role` filter is present, will only return role assignments that are granting that role.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        user (Union[Unset, None, str]): optional user filter, will only return role assignments
            granted to this user.
        role (Union[Unset, None, str]): optional role filter, will only return role assignments
            granting this role.
        tenant (Union[Unset, None, str]): optional tenant filter, will only return role
            assignments granted in that tenant.
        page (Union[Unset, None, int]): Page number of the results to fetch, starting at 1.
            Default: 1.
        per_page (Union[Unset, None, int]): The number of results per page (max 100). Default: 30.
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[HTTPValidationError, List[RoleAssignmentRead]]]
    """

    return (
        await asyncio_detailed(
            proj_id=proj_id,
            env_id=env_id,
            client=client,
            user=user,
            role=role,
            tenant=tenant,
            page=page,
            per_page=per_page,
            permit_session=permit_session,
        )
    ).parsed
