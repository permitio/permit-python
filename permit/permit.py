import copy
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Literal

from typing_extensions import Self

from permit.api.api_client import PermitApiClient
from permit.api.elements import ElementsApi
from permit.config import PermitConfig
from permit.enforcement.enforcer import (
    Action,
    CheckQuery,
    Enforcer,
    Resource,
    User,
)
from permit.enforcement.interfaces import AuthorizedUsersResult, TenantDetails
from permit.logger import configure_logger
from permit.pdp_api.pdp_api_client import PermitPdpApiClient
from permit.utils.context import Context
from permit.utils.sdk_logger import sdk_logger


class Permit:
    """The Permit SDK client (asyncio): authorization checks and the Permit REST API.

    Args:
        config: The SDK configuration.
        **options: `PermitConfig` fields, used to build the configuration when `config`
            is not given.
    """

    def __init__(self, config: PermitConfig | None = None, **options: Any) -> None:
        self._config: PermitConfig = config if config is not None else PermitConfig(**options)

        configure_logger(self._config)
        self._connect()
        sdk_logger.debug(
            f"Permit SDK initialized: api_url={self._config.api_url}, pdp={self._config.pdp}"
        )

    def _connect(self) -> None:
        """Create the clients that send this client's requests, from its config."""
        self._enforcer = Enforcer(self._config)
        self._api = PermitApiClient(self._config)
        self._elements = ElementsApi(self._config)
        self._pdp_api = PermitPdpApiClient(self._config)

    @property
    def config(self) -> PermitConfig:
        """Access the SDK configuration using this property.

        Once the SDK is initialized, the configuration is read-only.

        Usage example:

            permit = Permit(config)
            pdp_url = permit.config.pdp
        """
        return self._config.copy()

    @contextmanager
    def wait_for_sync(
        self, timeout: float = 10.0, policy: Literal["ignore", "fail"] | None = None
    ) -> Generator[Self, None, None]:
        """Context manager returning a client that waits for facts to be synced.

        Requests made through the returned client wait for the facts they write to be
        available in the PDP before proceeding.

        Args:
            timeout: The amount of time in seconds to wait for facts to be available in the PDP
            cache before returning the response.
            policy: Weather to fail the request when the timeout is reached or ignore.

            Set None to keep the default policy set in the instance config or the default value of
            PDP.

        Yields:
            Permit: A Permit instance that is configured to wait for facts to be synced.

        See Also:
            https://docs.permit.io/how-to/manage-data/local-facts-uploader
        """
        if not self._config.proxy_facts_via_pdp:
            sdk_logger.warning(
                "Tried to wait for synced facts but proxy_facts_via_pdp is disabled, ignoring..."
            )
            yield self
            return
        contextualized_config = self.config  # this copies the config
        contextualized_config.facts_sync_timeout = timeout
        if policy is not None:
            contextualized_config.facts_sync_timeout_policy = policy
        # A copy of this client that sends its requests with the new config. Creating a new
        # client instead would apply its log settings to the whole process again.
        waiting: Self = copy.copy(self)
        waiting._config = contextualized_config
        waiting._connect()
        yield waiting

    @property
    def api(self) -> PermitApiClient:
        """Access the Permit REST API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            await permit.api.roles.create(...)
        """
        return self._api

    @property
    def elements(self) -> ElementsApi:
        """Access the Permit Elements API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            await permit.elements.loginAs(user, tenant)
        """
        return self._elements

    @property
    def pdp_api(self) -> PermitPdpApiClient:
        """Access the Permit PDP API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            await permit.pdp_api.role_assignments.list()
        """
        return self._pdp_api

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
        return await self._enforcer.authorized_users(action, resource, context)

    async def bulk_check(
        self,
        checks: list[CheckQuery],
        context: Context | None = None,
    ) -> list[bool]:
        """Checks many authorization queries in a single request to the PDP.

        Args:
            checks: A list of check queries, each query contain user, action, and resource.
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
        return await self._enforcer.bulk_check(checks, context)

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
        return await self._enforcer.check(user, action, resource, context)

    async def get_user_permissions(
        self,
        user: User,
        tenants: list[str] | None = None,
        resources: list[str] | None = None,
        resource_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get all permissions for a user.

        Args:
            user: The user object or user key
            tenants: Optional list of tenants to filter permissions
            resources: Optional list of resources to filter
            resource_types: Optional list of resource types to filter

        Returns:
            dict: User permissions per tenant

        Raises:
            PermitConnectionError: If an error occurs while sending the request to the PDP
        """
        return await self._enforcer.get_user_permissions(user, tenants, resources, resource_types)

    async def get_user_tenants(
        self, user: User, context: Context | None = None
    ) -> list[TenantDetails]:
        """Get the tenants in which a user has a role, as the PDP knows them.

        The PDP lists a tenant when the user has a tenant-level role in it, the kind
        ``api.users.assign_role()`` grants. A role on a resource instance does not count, and
        neither does membership without a role, such as ``api.tenants.add_user()`` creates.
        The PDP answers from the data it has synced, so a change made through the API shows
        up once the PDP has it.

        Only the container PDP serves this query. The cloud PDP does not, and answers 404,
        which this method raises as a ``PermitConnectionError`` that says so.

        Args:
            user: The user key, or a user dict with a ``key`` and optionally ``attributes``,
                ``email``, ``first_name`` and ``last_name``, as ``check()`` takes it.
            context: The query's context, merged over the context store's base context.
                Defaults to None.

        Returns:
            list[TenantDetails]: The user's tenants, each with its key and attributes. Empty
                when the user has no tenant-level role or the PDP does not know the user.

        Raises:
            PermitConnectionError: If the PDP answers 404 (as the cloud PDP does), answers any
                other error status, or cannot be reached.

        Examples:
            # the tenants in which alice has a role
            tenants = await permit.get_user_tenants("alice")
            keys = [tenant.key for tenant in tenants]
        """
        return await self._enforcer.get_user_tenants(user, context)

    async def filter_objects(
        self, user: User, action: Action, context: Context, resources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter a list of resources, keeping only those the user is permitted to act on.

        Args:
            user: The user object or user key
            action: The action to check against every resource
            context: The context in which the action is performed
            resources: The resources to filter. Each entry may carry the keys
                `type`, `key`, `context`, `attributes` and `tenant`.

        Returns:
            list[dict[str, Any]]: The permitted subset of `resources`, in their original order

        Raises:
            PermitConnectionError: If an error occurs while sending the request to the PDP
        """
        return await self._enforcer.filter_objects(user, action, context, resources)
