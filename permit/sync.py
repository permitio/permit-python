import weakref
from types import TracebackType
from typing import Any, NoReturn

from typing_extensions import Self

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
from permit.utils.sync import _BackgroundLoop


# The blocking client keeps the blocking twins of the async client's helpers in the
# same attributes and returns plain values where the async base returns coroutines.
# That breaks substitutability on purpose, hence the assignment, override and
# return-value ignores below.
class Permit(AsyncPermit):
    """The Permit SDK client with a blocking interface.

    The client runs every blocking call on an event loop in a background daemon thread of
    its own, which it starts on the first call. Calls from any number of threads are handed
    to that thread and waited for, so they share the client's HTTP connections instead of
    each opening its own. Calling it from a thread that runs an event loop works too, and
    blocks that loop until the call returns, as any blocking call does.

    Close the client when done with it, with `close()` or a `with` block, to close its
    connections and stop the thread. A client that is never closed is cleaned up when it is
    garbage collected, or at interpreter exit; the thread never holds up the exit.

    Args:
        config: The SDK configuration.
        **options: `PermitConfig` fields, used to build the configuration when `config`
            is not given.

    Examples:
        with Permit(token="<YOUR_API_KEY>") as permit:
            permit.check("user", "read", "document")
    """

    def __init__(self, config: PermitConfig | None = None, **options: Any) -> None:
        # Before super().__init__, which calls _connect.
        self._background_loop = _BackgroundLoop()
        super().__init__(config, **options)
        # close() and the exit hook close the sessions while the client is alive. When the
        # client is collected, a finalizer closes them on the loop they belong to; it must
        # not keep the client alive, so it goes through a view of its attributes. Copies
        # made by wait_for_sync() use the sessions and the loop of the client that made
        # them, and leave closing both to it.
        self._background_loop.set_closer(weakref.WeakMethod(self._close_sessions))
        view = _view_of(self)
        close_sessions = view._close_sessions  # noqa: SLF001 - this class's own method
        self._background_loop.close_when_collected(self, close_sessions)

    def _connect(self) -> None:
        self._enforcer = SyncEnforcer(self._config)  # type: ignore[assignment]
        self._api = SyncPermitApiClient(self._config)  # type: ignore[assignment]
        self._elements = SyncElementsApi(self._config)  # type: ignore[assignment]
        self._pdp_api = SyncPDPApi(self._config)
        self._background_loop.bind(self._enforcer, self._api, self._elements, self._pdp_api)

    async def _close_sessions(self) -> None:
        """Close the HTTP sessions this client opened. Runs on its background loop."""
        await AsyncPermit.close(self)

    def close(self) -> None:  # type: ignore[override]
        """Close the client's HTTP connections and stop its background thread.

        It waits for the calls that other threads have in flight to return first. Calling it
        again does nothing. The client stays usable: the next call starts a new thread and
        opens new connections. A client yielded by `wait_for_sync()` runs its calls on the
        thread and over the connections of the client it was made from: its `close()` does
        nothing, and the other client's `close()` closes them.

        Raises:
            RuntimeError: If called on the client's own background thread, which it has to
                stop and join.

        Examples:
            permit = Permit(token="<YOUR_API_KEY>")
            try:
                permit.check("user", "read", "document")
            finally:
                permit.close()
        """
        if not self._owns_sessions:
            return
        self._background_loop.close()

    def __enter__(self) -> Self:
        """Return the client itself, which the end of the `with` block closes."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client, as `close()` does."""
        self.close()

    def __aenter__(self) -> NoReturn:
        """Refuse `async with`, which the blocking client does not support.

        Raises:
            TypeError: Always. A `with` block closes this client; `async with` is for the
                async client, `permit.Permit`.
        """
        msg = (
            "permit.sync.Permit is a blocking client: use `with Permit(...) as permit:`, not "
            "`async with`. In async code, use the async client, permit.Permit."
        )
        raise TypeError(msg)

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
        context: Context | None = None,
    ) -> dict[str, Any]:
        """Get all permissions for a user.

        Args:
            user: The user object or user key
            tenants: Optional list of tenants to filter permissions
            resources: Optional list of resources to filter
            resource_types: Optional list of resource types to filter
            context: The query's context, which ABAC policies can read, merged over the
                context store's base context as ``check()`` merges it. When it is None (the
                default), the request carries no context, and the base context is not sent
                either; pass ``{}`` to send the base context alone.

        Returns:
            dict: User permissions per tenant

        Raises:
            PermitConnectionError: If an error occurs while sending the request to the PDP
        """
        return self._enforcer.get_user_permissions(  # type: ignore[return-value]
            user, tenants, resources, resource_types, context
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


def _view_of(client: Permit) -> Permit:
    """A second object that shares `client`'s attributes, without keeping `client` alive.

    The two share one attribute dict, so the view sees every attribute set on the client
    after it was made. A finalizer of `client` can then close, through the view, the sessions
    that `client`'s attributes hold.
    """
    view = object.__new__(type(client))
    view.__dict__ = client.__dict__
    return view
