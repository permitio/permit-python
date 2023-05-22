from typing import Optional

from .api.elements import SyncElementsApi
from .api.sync_api_client import SyncPermitApiClient
from .config import PermitConfig
from .enforcement.enforcer import Action, Resource, SyncEnforcer, User
from .permit import Permit as AsyncPermit
from .utils.context import Context


class Permit(AsyncPermit):
    def __init__(self, config: Optional[PermitConfig] = None, **options):
        super().__init__(config, **options)
        self._enforcer = SyncEnforcer(self._config)
        self._api = SyncPermitApiClient(self._config)
        self._elements = SyncElementsApi(self._config)

    @property
    def api(self) -> SyncPermitApiClient:
        """
        Access the Permit REST API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            permit.api.roles.create(...)
        """
        return self._api

    @property
    def elements(self) -> SyncElementsApi:
        """
        Access the Permit Elements API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            permit.elements.loginAs(user, tenant)
        """
        return self._elements

    def check(
        self,
        user: User,
        action: Action,
        resource: Resource,
        context: Context = {},
    ) -> bool:
        """
        Checks if a user is authorized to perform an action on a resource within the specified context.

        Args:
            user: The user object representing the user.
            action: The action to be performed on the resource.
            resource: The resource object representing the resource.
            context: The context object representing the context in which the action is performed. Defaults to None.

        Returns:
            bool: True if the user is authorized, False otherwise.

        Raises:
            PermitConnectionError: If an error occurs while sending the authorization request to the PDP.

        Examples:

            # can the user close any issue?
            permit.check(user, 'close', 'issue')

            # can the user close any issue who's id is 1234?
            permit.check(user, 'close', 'issue:1234')

            # can the user close (any) issues belonging to the 't1' tenant?
            # (in a multi tenant application)
            permit.check(user, 'close', {'type': 'issue', 'tenant': 't1'})
        """
        return self._enforcer.check(user, action, resource, context)
