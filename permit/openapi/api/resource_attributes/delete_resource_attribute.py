from typing import Any, Dict, Optional, Union, cast

import httpx

from ..utils import parse_response
from ...client import AuthenticatedClient
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    proj_id: str,
    env_id: str,
    resource_id: str,
    attribute_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Dict[str, Any]:
    url = "{}/v2/schema/{proj_id}/{env_id}/resources/{resource_id}/attributes/{attribute_id}".format(
        client.base_url,
        proj_id=proj_id,
        env_id=env_id,
        resource_id=resource_id,
        attribute_id=attribute_id,
    )

    headers: Dict[str, str] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    if permit_session is not UNSET:
        cookies["permit_session"] = permit_session

    return {
        "method": "delete",
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[Any, HTTPValidationError]]:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[Any, HTTPValidationError]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=parse_response(response=response, model=Any),
    )


def sync_detailed(
    proj_id: str,
    env_id: str,
    resource_id: str,
    attribute_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[Any, HTTPValidationError]]:
    """Delete Resource Attribute

     Deletes the attribute and all its related data.

    Note: If the attribute is used by policies, removing it will cause the
    attribute to evaluate as `undefined`.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        attribute_id (str): Either the unique id of the attribute, or the URL-friendly key of the
            attribute (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[Any, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        resource_id=resource_id,
        attribute_id=attribute_id,
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
    resource_id: str,
    attribute_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, HTTPValidationError]]:
    """Delete Resource Attribute

     Deletes the attribute and all its related data.

    Note: If the attribute is used by policies, removing it will cause the
    attribute to evaluate as `undefined`.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        attribute_id (str): Either the unique id of the attribute, or the URL-friendly key of the
            attribute (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[Any, HTTPValidationError]]
    """

    return sync_detailed(
        proj_id=proj_id,
        env_id=env_id,
        resource_id=resource_id,
        attribute_id=attribute_id,
        client=client,
        permit_session=permit_session,
    ).parsed


async def asyncio_detailed(
    proj_id: str,
    env_id: str,
    resource_id: str,
    attribute_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Response[Union[Any, HTTPValidationError]]:
    """Delete Resource Attribute

     Deletes the attribute and all its related data.

    Note: If the attribute is used by policies, removing it will cause the
    attribute to evaluate as `undefined`.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        attribute_id (str): Either the unique id of the attribute, or the URL-friendly key of the
            attribute (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[Any, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        proj_id=proj_id,
        env_id=env_id,
        resource_id=resource_id,
        attribute_id=attribute_id,
        client=client,
        permit_session=permit_session,
    )

    async with httpx.AsyncClient(verify=client.verify_ssl) as _client:
        response = await _client.request(**kwargs)

    return _build_response(response=response)


async def asyncio(
    proj_id: str,
    env_id: str,
    resource_id: str,
    attribute_id: str,
    *,
    client: AuthenticatedClient,
    permit_session: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, HTTPValidationError]]:
    """Delete Resource Attribute

     Deletes the attribute and all its related data.

    Note: If the attribute is used by policies, removing it will cause the
    attribute to evaluate as `undefined`.

    Args:
        proj_id (str): Either the unique id of the project, or the URL-friendly key of the project
            (i.e: the "slug").
        env_id (str): Either the unique id of the environment, or the URL-friendly key of the
            environment (i.e: the "slug").
        resource_id (str): Either the unique id of the resource, or the URL-friendly key of the
            resource (i.e: the "slug").
        attribute_id (str): Either the unique id of the attribute, or the URL-friendly key of the
            attribute (i.e: the "slug").
        permit_session (Union[Unset, str]):

    Returns:
        Response[Union[Any, HTTPValidationError]]
    """

    return (
        await asyncio_detailed(
            proj_id=proj_id,
            env_id=env_id,
            resource_id=resource_id,
            attribute_id=attribute_id,
            client=client,
            permit_session=permit_session,
        )
    ).parsed
