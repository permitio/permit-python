import json
from http import HTTPStatus
from pprint import pformat
from typing import TYPE_CHECKING, Any, Union

import aiohttp
from aiohttp import ClientTimeout
from loguru import logger
from typing_extensions import NotRequired, TypedDict

from permit.config import PermitConfig
from permit.enforcement.interfaces import AuthorizedUsersResult, ResourceInput, UserInput
from permit.exceptions import PermitConnectionError
from permit.utils.context import Context, ContextStore
from permit.utils.dicts import deep_merge
from permit.utils.pydantic_version import PYDANTIC_VERSION
from permit.utils.sync import SyncClass

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import parse_obj_as
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import parse_obj_as
else:
    from pydantic.v1 import parse_obj_as


RESOURCE_DELIMITER = ":"

# Public aliases kept exactly as they were (bare `dict`, `typing.Union`): unlike a
# parameterized form, they still work in `isinstance(value, User)`.
User = Union[dict, str]  # type: ignore[type-arg]  # noqa: UP007
Action = str
Resource = Union[dict, str]  # type: ignore[type-arg]  # noqa: UP007

# A resource string is "type" or "type:key".
_MAX_RESOURCE_STRING_PARTS = 2


async def read_error_body(response: aiohttp.ClientResponse) -> str:
    """Read an error response body without assuming it is JSON.

    The PDP returns its auth rejections as plain text with no content-type
    header, so calling ``.json()`` on them raises ``aiohttp.ContentTypeError``
    -- which is an ``aiohttp.ClientError``, and is therefore swallowed by the
    surrounding handler and re-reported as "cannot connect to the PDP
    container". A 403 for a wrong API key was indistinguishable from the PDP
    being down, which is a genuinely misleading error to hand a user.
    """
    try:
        return repr(await response.json())
    except (aiohttp.ClientError, ValueError):
        pass
    try:
        text = (await response.text()).strip()
    except aiohttp.ClientError:
        return "<error body could not be read>"
    return text or "<empty error body>"


class CheckQuery(TypedDict):
    """One authorization query of a `bulk_check()` call."""

    user: User
    action: Action
    resource: Resource
    context: NotRequired[Context | None]


SETUP_PDP_DOCS_LINK = "https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"


class _TimeoutConfig(TypedDict, total=False):
    timeout: ClientTimeout


class Enforcer:
    """Sends authorization queries to the PDP."""

    def __init__(self, config: PermitConfig) -> None:
        self._config = config
        self._context_store = ContextStore()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {self._config.token}",
        }
        self._base_url = self._config.pdp

    @property
    def context_store(self) -> ContextStore:
        """The base context merged into every query.

        It is exposed so the application can set up flexible contextual behavior for
        authorization queries.
        """
        return self._context_store

    @property
    def _timeout_config(self) -> _TimeoutConfig:
        timeout_config: _TimeoutConfig = {}
        if self._config.pdp_timeout is not None:
            timeout_config["timeout"] = ClientTimeout(total=self._config.pdp_timeout)
        return timeout_config

    async def authorized_users(
        self,
        action: Action,
        resource: Resource,
        context: Context | None = None,
    ) -> AuthorizedUsersResult:
        """Get all the users authorized to perform an action on a resource in a context.

        Args:
            action: The action to be performed on the resource.
            resource: The resource object representing the resource.
            context: The context object representing the context in which the action is performed.
                Defaults to None.

        Returns:
            AuthorizedUsersResult: Contains all the authorized users and the role assignments that
                granted the permission.

        Raises:
            PermitConnectionError: If an error occurs while sending the authorization request to the
                PDP.

        Examples:
            # all the users that can close any issue?
            await permit.authorized_users('close', 'issue')

            # all the users that can close an issue who's id is 1234?
            await permit.authorized_users('close', 'issue:1234')

            # all the users that can close (any) issues belonging to the 't1' tenant?
            # (in a multi tenant application)
            await permit.authorized_users('close', {'type': 'issue', 'tenant': 't1'})
        """
        context = context or {}

        normalized_resource: ResourceInput = self._normalize_resource(
            self._resource_from_string(resource)
            if isinstance(resource, str)
            else ResourceInput(**resource)
        )
        query_context = self._context_store.get_derived_context(context)
        request_body = {
            "action": action,
            "resource": normalized_resource.dict(exclude_unset=True),
            "context": query_context,
        }

        async with aiohttp.ClientSession(headers=self._headers, **self._timeout_config) as session:
            check_url = f"{self._base_url}/authorized_users"
            try:
                async with session.post(
                    check_url,
                    data=json.dumps(request_body),
                ) as response:
                    if response.status != HTTPStatus.OK:
                        if response.status == HTTPStatus.NOT_IMPLEMENTED:
                            msg = (
                                f"Permit SDK got an error: {response.status}, "
                                f"and cannot connect to the PDP container."
                                f"\nPlease ensure you are not using ABAC/ReBAC policies,"
                                f"as the cloud PDP is not compatible with these kinds "
                                f"of policies.\n"
                                f"Also, please check your configuration and "
                                f"make sure it's running at {self._base_url} "
                                f"and accepting requests.\n"
                                f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                            )
                            raise PermitConnectionError(msg)

                        error_body = await read_error_body(response)
                        logger.error(
                            "error in permit.authorized_users({}, {}):\n{}\n{}".format(
                                action,
                                self._resource_repr(normalized_resource),
                                f"status code: {response.status}",
                                error_body,
                            )
                        )
                        msg = (
                            f"Permit SDK got unexpected status code: {response.status} "
                            f"from the PDP at {self._base_url}.\nResponse body: {error_body}\n"
                            f"The PDP is reachable, so this is a rejected request rather than a "
                            f"connectivity problem -- a 401/403 usually means the PDP was started "
                            f"with a different API key than the SDK is using.\n"
                            f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                        )
                        raise PermitConnectionError(msg)

                    content: dict[str, Any] = await response.json()
                    logger.debug(
                        f"permit.authorized_users() response:"
                        f"\ninput: {pformat(request_body, indent=2)}"
                        f"\nresponse status: {response.status}"
                        f"\nresponse data: {pformat(content, indent=2)}"
                    )
                    result: AuthorizedUsersResult = parse_obj_as(AuthorizedUsersResult, content)
                    return result
            except aiohttp.ClientError as err:
                logger.error(
                    f"error in permit.authorized_users({action}, "
                    f"{self._resource_repr(normalized_resource)}):\n{err}"
                )
                msg = (
                    f"Permit SDK got error: {err}, and cannot connect to the PDP container.\n"
                    f"Please check your configuration and make sure it's running at "
                    f"{self._base_url} and accepting requests.\n "
                    f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                )
                raise PermitConnectionError(
                    msg,
                    error=err,
                ) from err

    async def bulk_check(
        self,
        checks: list[CheckQuery],
        context: Context | None = None,
    ) -> list[bool]:
        """Checks if a user is authorized to perform an action on a resource in a context.

        Args:
            checks: A list of CheckQuery objects representing the authorization queries to be
                performed.
                Each check may carry its own ``context``, which is merged over the method-level
                ``context`` for that check only.
            context: The context object representing the context in which the action is performed.
                Defaults to None.

        Returns:
            list[bool]: A list of booleans indicating whether the user is authorized for each
                resource.

        Raises:
            PermitConnectionError: If an error occurs while sending the authorization request to the
                PDP.

        Examples:
            # Bulk query of multiple check conventions
            await permit.bulk_check([
                {
                    "user": user,
                    "action": "close",
                    "resource": {type: "issue", key: "1234"},
                },
                {
                    "user": {key: "user"},
                    "action": "close",
                    "resource": "issue:1235",
                },
                {
                    "user": "user_a",
                    "action": "close",
                    "resource": "issue",
                },
            ])
        """
        context = context or {}
        request_body = []
        for check in checks:
            normalized_user: UserInput = (
                UserInput(key=check["user"])
                if isinstance(check["user"], str)
                else UserInput(**check["user"])
            )
            normalized_resource: ResourceInput = self._normalize_resource(
                self._resource_from_string(check["resource"])
                if isinstance(check["resource"], str)
                else ResourceInput(**check["resource"])
            )
            check_context: Context = check.get("context") or {}
            query_context = self._context_store.get_derived_context(
                deep_merge(context, check_context)
            )
            request_body.append(
                {
                    "user": normalized_user.dict(exclude_unset=True),
                    "action": check["action"],
                    "resource": normalized_resource.dict(exclude_unset=True),
                    "context": query_context,
                }
            )

        async with aiohttp.ClientSession(headers=self._headers, **self._timeout_config) as session:
            check_url = f"{self._base_url}/allowed/bulk"
            try:
                async with session.post(
                    check_url,
                    data=json.dumps(request_body),
                ) as response:
                    if response.status != HTTPStatus.OK:
                        error_body = await read_error_body(response)
                        msg = "error in permit.check({}):\n{}\n{}".format(
                            (
                                [
                                    [
                                        check.get("user"),
                                        check.get("action"),
                                        check.get("resource"),
                                    ]
                                    for check in request_body
                                ]
                            ),
                            f"status code: {response.status}",
                            error_body,
                        )
                        logger.error(msg)
                        raise PermitConnectionError(msg)
                    content: dict[str, Any] = await response.json()
                    logger.debug(
                        f"permit.check() response:\n"
                        f"input: {pformat(request_body, indent=2)}\n"
                        f"response status: {response.status}\n"
                        f"response data: {pformat(content, indent=2)}"
                    )
                    data = content.get("allow", content.get("result", {}).get("allow", []))
                    decisions: list[bool] = [bool(item.get("allow", False)) for item in data]
            except aiohttp.ClientError as err:
                msg = "error in permit.check({}):\n{}".format(
                    (
                        [
                            [
                                check.get("user"),
                                check.get("action"),
                                check.get("resource"),
                            ]
                            for check in request_body
                        ]
                    ),
                    err,
                )
                logger.error(msg)
                raise PermitConnectionError(msg, error=err) from err
            return decisions

    async def check(
        self,
        user: User,
        action: Action,
        resource: Resource,
        context: Context | None = None,
    ) -> bool:
        """Checks if a user is authorized to perform an action on a resource in a context.

        Args:
            user: The user object representing the user.
            action: The action to be performed on the resource.
            resource: The resource object representing the resource.
            context: The context object representing the context in which the action is performed.
                Defaults to None.

        Returns:
            bool: True if the user is authorized, False otherwise.

        Raises:
            PermitConnectionError: If an error occurs while sending the authorization request to the
                PDP.

        Examples:
            # can the user close any issue?
            await permit.check(user, 'close', 'issue')

            # can the user close any issue who's id is 1234?
            await permit.check(user, 'close', 'issue:1234')

            # can the user close (any) issues belonging to the 't1' tenant?
            # (in a multi tenant application)
            await permit.check(user, 'close', {'type': 'issue', 'tenant': 't1'})
        """
        context = context or {}

        normalized_user: UserInput = (
            UserInput(key=user) if isinstance(user, str) else UserInput(**user)
        )
        normalized_resource: ResourceInput = self._normalize_resource(
            self._resource_from_string(resource)
            if isinstance(resource, str)
            else ResourceInput(**resource)
        )
        query_context = self._context_store.get_derived_context(context)
        body = {
            "user": normalized_user.dict(exclude_unset=True),
            "action": action,
            "resource": normalized_resource.dict(exclude_unset=True),
            "context": query_context,
        }
        async with aiohttp.ClientSession(headers=self._headers, **self._timeout_config) as session:
            check_url = f"{self._base_url}/allowed"
            try:
                async with session.post(
                    check_url,
                    data=json.dumps(body),
                ) as response:
                    if response.status != HTTPStatus.OK:
                        if response.status == HTTPStatus.NOT_IMPLEMENTED:
                            msg = (
                                f"Permit SDK got an error: {response.status}, "
                                f"and cannot connect to the PDP container."
                                f"\nPlease ensure you are not using ABAC/ReBAC policies,\n"
                                f"as the cloud PDP is not compatible with these kinds "
                                f"of policies.\n"
                                f"Also, please check your configuration and make sure it's running "
                                f"at {self._base_url} and accepting requests.\n"
                                f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                            )
                            raise PermitConnectionError(msg)

                        error_body = await read_error_body(response)
                        logger.error(
                            "error in permit.check({}, {}, {}):\n{}\n{}".format(
                                normalized_user,
                                action,
                                self._resource_repr(normalized_resource),
                                f"status code: {response.status}",
                                error_body,
                            )
                        )
                        msg = (
                            f"Permit SDK got unexpected status code: {response.status} "
                            f"from the PDP at {self._base_url}.\nResponse body: {error_body}\n"
                            f"The PDP is reachable, so this is a rejected request rather than a "
                            f"connectivity problem -- a 401/403 usually means the PDP was started "
                            f"with a different API key than the SDK is using.\n"
                            f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                        )
                        raise PermitConnectionError(msg)

                    content: dict[str, Any] = await response.json()
                    logger.debug(
                        f"permit.check() response:\n"
                        f"body: {pformat(body, indent=2)}\n"
                        f"response status: {response.status}\n"
                        f"response data: {pformat(content, indent=2)}"
                    )
                    decision: bool = bool(content.get("allow", False))
                    return decision
            except aiohttp.ClientError as err:
                logger.error(
                    f"error in permit.check({normalized_user}, {action}, "
                    f"{self._resource_repr(normalized_resource)}):"
                    f"\n{err}"
                )
                msg = (
                    f"Permit SDK got error: {err}, \n"
                    f"and cannot connect to the PDP container, please check your configuration "
                    f"and make sure it's "
                    f"running at {self._base_url} and accepting requests. \n"
                    f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                )
                raise PermitConnectionError(
                    msg,
                    error=err,
                ) from err

    async def get_user_permissions(
        self,
        user: dict[str, Any] | str,
        tenants: list[str] | None = None,
        resources: list[str] | None = None,
        resource_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get all permissions of a user.

        Args:
            user: The user object or user key.
            tenants: Only return permissions in these tenants.
            resources: Only return permissions on these resources.
            resource_types: Only return permissions on these resource types.

        Returns:
            The user's permissions per tenant and resource.

        Raises:
            PermitConnectionError: If the PDP rejects the request or cannot be reached.
        """
        input_data = {
            "user": {"key": user} if isinstance(user, str) else user,
            "tenants": tenants,
            "resources": resources,
            "resource_types": resource_types,
        }

        async with aiohttp.ClientSession(headers=self._headers, **self._timeout_config) as session:
            url = f"{self._base_url}/user-permissions"
            try:
                async with session.post(
                    url,
                    data=json.dumps(input_data),
                ) as response:
                    if response.status != HTTPStatus.OK:
                        msg = (
                            f"Permit.getUserPermissions() got an unexpected status code: "
                            f"{response.status}, "
                            f"please check your SDK init and make sure the PDP sidecar "
                            f"is configured correctly.\n"
                            f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                        )
                        raise PermitConnectionError(msg)

                    content = await response.json()
                    permissions: dict[str, Any] = (
                        content.get("result", {}).get("permissions", {})
                        if "result" in content
                        else content
                    )

                    logger.debug(
                        f"permit.get_user_permissions() response:\n"
                        f"input: {pformat(input_data, indent=2)}\n"
                        f"response data: {pformat(permissions, indent=2)}"
                    )
                    return permissions

            except aiohttp.ClientError as err:
                logger.error(f"Error in permit.get_user_permissions(): {err}")
                msg = (
                    f"Permit SDK got error: {err}, \n"
                    f"and cannot connect to the PDP container, please check your configuration "
                    f"and make sure it's "
                    f"running at {self._base_url} and accepting requests. \n"
                    f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
                )
                raise PermitConnectionError(
                    msg,
                    error=err,
                ) from err

    async def filter_objects(
        self, user: User, action: Action, context: Context, resources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter the given resources down to the ones the user is allowed to act on.

        Args:
            user: The user object representing the user.
            action: The action to be performed on each resource.
            context: The context every check is evaluated against.
            resources: The resources to filter. Each resource may carry its own ``context``
                key, which is sent as the resource context of that check.

        Returns:
            list[dict]: The subset of ``resources`` the user is authorized for, in input order.
        """
        requests: list[CheckQuery] = []
        for resource in resources:
            permit_resource: dict[str, Any] = {
                "type": resource.get("type"),
                "key": resource.get("key"),
                "context": resource.get("context", {}),
                "attributes": resource.get("attributes", {}),
                "tenant": resource.get("tenant"),
            }
            check_query: CheckQuery = {
                "user": user,
                "action": action,
                "resource": permit_resource,
                "context": context,
            }
            requests.append(check_query)

        results = await self.bulk_check(requests, context=context)
        filtered_resources: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if result:
                filtered_resources.append(resources[i])
        return filtered_resources

    def _normalize_resource(self, resource: ResourceInput) -> ResourceInput:
        normalized_resource: ResourceInput = resource.copy()
        if normalized_resource.context is None:
            normalized_resource.context = {}

        # if tenant is empty, we might auto-set the default tenant according to config
        if (
            normalized_resource.tenant is None
            and self._config.multi_tenancy.use_default_tenant_if_empty
        ):
            normalized_resource.tenant = self._config.multi_tenancy.default_tenant

        # copy tenant from resource.tenant to resource.context.tenant (until we change RBAC policy)
        if (
            normalized_resource.context.get("tenant", None) is None
            and normalized_resource.tenant is not None
        ):
            normalized_resource.context["tenant"] = normalized_resource.tenant
        return normalized_resource

    @staticmethod
    def _resource_repr(resource: ResourceInput) -> str:
        resource_repr: str = resource.type
        if resource.key is not None:
            resource_repr += ":" + resource.key
        if resource.tenant:
            resource_repr += f", tenant: {resource.tenant}"
        return resource_repr

    @staticmethod
    def _resource_from_string(resource: str) -> ResourceInput:
        parts = resource.split(RESOURCE_DELIMITER)
        if len(parts) < 1 or len(parts) > _MAX_RESOURCE_STRING_PARTS:
            msg = f"permit.check() got invalid resource string: {resource}"
            raise ValueError(msg)
        return ResourceInput(type=parts[0], key=(parts[1] if len(parts) > 1 else None))


class SyncEnforcer(Enforcer, metaclass=SyncClass):
    """Blocking variant of `Enforcer`."""
