import json
from typing import Optional

from loguru import logger

from .api.api_client import PermitApiClient
from .api.elements import ElementsApi
from .config import PermitConfig
from .enforcement.enforcer import Action, CheckQuery, Enforcer, Resource, User
from .logger import configure_logger
from .pdp_api.pdp_api import PdpApi
from .utils.context import Context


class Permit:
    def __init__(self, config: Optional[PermitConfig] = None, **options):
        self._config: PermitConfig = (
            config if config is not None else PermitConfig(**options)
        )

        configure_logger(self._config)
        self._enforcer = Enforcer(self._config)
        self._api = PermitApiClient(self._config)
        self._elements = ElementsApi(self._config)
        self._pdp_api = PdpApi(self._config)

        logger.debug(
            "Permit SDK initialized with config:\n${}",
            json.dumps(self._config.dict(exclude={"api_context"})),
        )

    @property
    def config(self):
        """
        Access the SDK configuration using this property.
        Once the SDK is initialized, the configuration is read-only.

        Usage example:

            permit = Permit(config)
            pdp_url = permit.config.pdp
        """
        return self._config.copy()

    @property
    def api(self) -> PermitApiClient:
        """
        Access the Permit REST API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            await permit.api.roles.create(...)
        """
        return self._api

    @property
    def elements(self) -> ElementsApi:
        """
        Access the Permit Elements API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            await permit.elements.loginAs(user, tenant)
        """
        return self._elements

    @property
    def pdp(self) -> PdpApi:
        """
        Access the Permit PDP API using this property.

        Usage example:

            permit = Permit(token
            await permit.pdp.list_role_assignments()
        """
        return self._pdp_api

    async def bulk_check(
        self,
        checks: list[CheckQuery],
        context: Context = {},
    ) -> list[bool]:
        """
        Checks if a user is authorized to perform an action on a list of resources within the specified context.

        Args:
            checks: A list of check queries, each query contain user, action, and resource.
            context: The context object representing the context in which the action is performed. Defaults to None.

        Returns:
            list[bool]: A list of booleans indicating whether the user is authorized for each resource.

        Raises:
            PermitConnectionError: If an error occurs while sending the authorization request to the PDP.

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
            await permit.check(user, 'close', 'issue')

            # can the user close any issue who's id is 1234?
            await permit.check(user, 'close', 'issue:1234')

            # can the user close (any) issues belonging to the 't1' tenant?
            # (in a multi tenant application)
            await permit.check(user, 'close', {'type': 'issue', 'tenant': 't1'})
        """
        return await self._enforcer.check(user, action, resource, context)
