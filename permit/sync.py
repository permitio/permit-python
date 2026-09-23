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
from permit.enforcement.interfaces import AuthorizedUsersResult
from permit.pdp_api.pdp_api_client import SyncPDPApi
from permit.permit import Permit as AsyncPermit
from permit.utils.context import Context


# The overrides below return plain values where the async base class returns
# coroutines. That breaks substitutability on purpose -- it is what makes this the
# blocking client -- hence the `override` and `return-value` ignores.
class Permit(AsyncPermit):
    """The Permit SDK client with a blocking interface.

    Args:
        config: The SDK configuration.
        **options: `PermitConfig` fields, used to build the configuration when `config`
            is not given.
    """

    def __init__(self, config: PermitConfig | None = None, **options: Any) -> None:
        super().__init__(config, **options)
        self._enforcer = SyncEnforcer(self._config)
        self._api = SyncPermitApiClient(self._config)  # type: ignore[assignment]
        self._elements = SyncElementsApi(self._config)
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
    def elements(self) -> SyncElementsApi:
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
