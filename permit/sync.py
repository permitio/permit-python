from typing import Any

from permit.api.elements import SyncElementsApi
from permit.api.sync_api_client import SyncPermitApiClient
from permit.config import PermitConfig
from permit.enforcement.enforcer import (
    Action,
    CheckQuery,
    Resource,
    SyncEnforcer,
    User,
)
from permit.enforcement.interfaces import AuthorizedUsersResult, TenantDetails
from permit.pdp_api.pdp_api_client import SyncPDPApi
from permit.permit import Permit as AsyncPermit
from permit.utils.context import Context


# The blocking client keeps the blocking twins of the async client's helpers in the
# same attributes and returns plain values where the async base returns coroutines.
# That breaks substitutability on purpose, hence the assignment, override and
# return-value ignores below.
class Permit(AsyncPermit):
    """The Permit SDK client with a blocking interface.

    Args:
        config: The SDK configuration.
        **options: `PermitConfig` fields, used to build the configuration when `config`
            is not given.
    """

    def __init__(self, config: PermitConfig | None = None, **options: Any) -> None:
        super().__init__(config, **options)

    def _connect(self) -> None:
        self._enforcer = SyncEnforcer(self._config)  # type: ignore[assignment]
        self._api = SyncPermitApiClient(self._config)  # type: ignore[assignment]
        self._elements = SyncElementsApi(self._config)  # type: ignore[assignment]
        self._pdp_api = SyncPDPApi(self._config)

    @property
    def api(self) -> SyncPermitApiClient:  # type: ignore[override]
        """Access the Permit REST API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            permit.api.roles.create(...)
        """
        return self._api  # type: ignore[return-value]

    @property
    def elements(self) -> SyncElementsApi:  # type: ignore[override]
        """Access the Permit Elements API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            permit.elements.loginAs(user, tenant)
        """
        return self._elements  # type: ignore[return-value]

    @property
    def pdp_api(self) -> SyncPDPApi:
        """Access the Permit PDP API using this property.

        Usage example:
        permit = Permit(token="<YOUR_API_KEY>")
        permit.pdp_api.role_assignments(...)
        """
        return self._pdp_api  # type: ignore[return-value]

    def bulk_check(  # type: ignore[override]
        self,
        checks: list[CheckQuery],
        context: Context | None = None,
    ) -> list[bool]:
        """Checks many authorization queries in a single request to the PDP.

        Args:
            checks: A list of CheckQuery objects representing the authorization checks to be
                performed.
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
        return self._enforcer.bulk_check(checks, context)  # type: ignore[return-value]

    def check(  # type: ignore[override]
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
            permit.check(user, 'close', 'issue')

            # can the user close any issue who's id is 1234?
            permit.check(user, 'close', 'issue:1234')

            # can the user close (any) issues belonging to the 't1' tenant?
            # (in a multi tenant application)
            permit.check(user, 'close', {'type': 'issue', 'tenant': 't1'})
        """
        return self._enforcer.check(user, action, resource, context)  # type: ignore[return-value]

    def authorized_users(  # type: ignore[override]
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
            permit.authorized_users('close', 'issue')

            # all the users that can close an issue who's id is 1234?
            permit.authorized_users('close', 'issue:1234')

            # all the users that can close (any) issues belonging to the 't1' tenant?
            # (in a multi tenant application)
            permit.authorized_users('close', {'type': 'issue', 'tenant': 't1'})
        """
        return self._enforcer.authorized_users(action, resource, context)  # type: ignore[return-value]

    def get_user_permissions(  # type: ignore[override]
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
        return self._enforcer.get_user_permissions(  # type: ignore[return-value]
            user, tenants, resources, resource_types
        )

    def get_user_tenants(  # type: ignore[override]
        self, user: User, context: Context | None = None
    ) -> list[TenantDetails]:
        """Get the tenants in which a user has a role, as the PDP knows them.

        The PDP lists a tenant when the user has a tenant-level role in it, the kind
        ``api.users.assign_role()`` grants. A role on a resource instance does not count, and
        neither does membership without a role, such as ``api.tenants.create_user()`` creates.
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
            tenants = permit.get_user_tenants("alice")
            keys = [tenant.key for tenant in tenants]
        """
        return self._enforcer.get_user_tenants(user, context)  # type: ignore[return-value]

    def filter_objects(  # type: ignore[override]
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
        return self._enforcer.filter_objects(user, action, context, resources)  # type: ignore[return-value]
