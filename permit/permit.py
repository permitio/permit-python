import json
from contextlib import contextmanager
from typing import Generator, Optional

from loguru import logger
from permit_datafilter.boolean_expression.schemas import ResidualPolicyResponse
from pydantic import NonNegativeFloat
from typing_extensions import Self

from .api.api_client import PermitApiClient
from .api.elements import ElementsApi
from .config import PermitConfig
from .enforcement.enforcer import (
    Action,
    AuthorizedUsersResult,
    CheckQuery,
    Enforcer,
    Resource,
    User,
)
from .logger import configure_logger
from .pdp_api.pdp_api_client import PermitPdpApiClient
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
        self._pdp_api = PermitPdpApiClient(self._config)
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

    @contextmanager
    def wait_for_sync(self, timeout: float = 10.0) -> Generator[Self, None, None]:
        """
        Context manager that returns a client that is configured
        to wait for facts to be synced before proceeding.


        Args:
            timeout: The amount of time in seconds to wait for facts to be available in the PDP
            cache before returning the response.

        Yields:
            Permit: A Permit instance that is configured to wait for facts to be synced.

        See Also:
            https://docs.permit.io/how-to/manage-data/local-facts-uploader
        """
        if not self._config.proxy_facts_via_pdp:
            logger.warning(
                "Tried to wait for synced facts but proxy_facts_via_pdp is disabled, ignoring..."
            )
            yield self
            return
        contextualized_config = self.config  # this copies the config
        contextualized_config.facts_sync_timeout = timeout
        yield self.__class__(contextualized_config)

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
    def pdp_api(self) -> PermitPdpApiClient:
        """
        Access the Permit PDP API using this property.

        Usage example:

            permit = Permit(token="<YOUR_API_KEY>")
            await permit.pdp_api.role_assignments.list()
        """
        return self._pdp_api

    async def authorized_users(
        self,
        action: Action,
        resource: Resource,
        context: Context = {},
    ) -> AuthorizedUsersResult:
        """
        Queries to get all the users that are authorized to perform an action on a resource within the specified context.

        Args:
            action: The action to be performed on the resource.
            resource: The resource object representing the resource.
            context: The context object representing the context in which the action is performed. Defaults to None.

        Returns:
            AuthorizedUsersResult: Contains all the authorized users and the role assignments that granted the permission.

        Raises:
            PermitConnectionError: If an error occurs while sending the authorization request to the PDP.

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

    async def filter_resources(
        self,
        user: User,
        action: Action,
        resource_type: str,
        context: Context = {},
    ) -> ResidualPolicyResponse:
        """
        Returns a filter that can be applied to the user database that filters all the resources a user can access given a user, action and resource type.

        The filter is a residual policy compiled from OPA Rego AST and transformed to be expressed as a boolean expression
        (combination of logical and comparison operators, where the operands can be variable references or literal values).

        An example for a residual policy:
        {
            "type": "conditional",
            "condition": {
                "expression": {
                    "operator": "eq",
                    "operands": [
                        {
                            "variable": "input.resource.tenant"
                        },
                        {
                            "value": "082f6978-6424-4e05-a706-1ab6f26c3768"
                        }
                    ]
                }
            }
        }

        The user can then map this residual policy into an SQL expression using various plugins.

        Args:
            user: The user object representing the user.
            action: The action to be performed on the resource.
            resource_type: The resource type.
            context: The context object representing the context in which the action is performed. Defaults to None.

        Returns:
            ResidualPolicyResponse: a residual policy that can be transformed into an SQL expression.

        Raises:
            PermitConnectionError: If an error occurs while sending the authorization request to the PDP.

        Examples:

            from sqlalchemy.orm import declarative_base, relationship

            from permit import Permit
            from permit_datafilter.plugins.sqlalchemy import QueryBuilder

            # assuming we have the following SQL tables:
            Base = declarative_base()

            class Tenant(Base):
                __tablename__ = "tenant"

                id = Column(String, primary_key=True)
                key = Column(String(255))

            class Task(Base):
                __tablename__ = "task"

                id = Column(String, primary_key=True)
                created_at = Column(DateTime, default=datetime.utcnow())
                updated_at = Column(DateTime)
                description = Column(String(255))
                tenant_id = Column(String, ForeignKey("tenant.id"))
                tenant = relationship("Tenant", backref="tasks")

            # this is how we can filter all the task records in the database
            # that are readable by the user according to the authz policy
            # (i.e: that user have the `task:read` permission on them)
            permit = Permit(...)
            authz_filter = await permit.filter_resources("john@doe.com", "read", "task")
            query = (
                QueryBuilder()
                    .select(Task)
                    .filter_by(authz_filter)
                    .map_references({
                        # if mapping a reference to a field on a related table
                        "input.resource.tenant": Tenant.key,
                    })
                    # you must specify how to perform a join against that table
                    .join(Tenant, Task.tenant_id == Tenant.id)
                    .build()
            )
        """
        return await self._enforcer.filter_resources(
            user, action, resource_type, context
        )
