import json
from pprint import pformat
from typing import Union

import aiohttp
from aiohttp import ClientTimeout
from loguru import logger
from permit_datafilter.boolean_expression.schemas import ResidualPolicyResponse
from pydantic import parse_obj_as

from ..config import PermitConfig
from ..exceptions import PermitConnectionError
from ..utils.context import Context, ContextStore
from ..utils.sync import SyncClass
from .interfaces import AuthorizedUsersResult, ResourceInput, UserInput


def set_if_not_none(d: dict, k: str, v):
    if v is not None:
        d[k] = v


RESOURCE_DELIMITER = ":"

User = Union[dict, str]
Action = str
Resource = Union[dict, str]

CheckQuery = {
    "user": User,
    "action": Action,
    "resource": Resource,
}


class Enforcer:
    def __init__(self, config: PermitConfig):
        self._config = config
        self._context_store = ContextStore()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {self._config.token}",
        }
        self._base_url = self._config.pdp

    @property
    def context_store(self):
        """
        we let context store be accessed from the outside so that the
        using app can setup a flexible contextual behavior for authorization queries
        """
        return self._context_store

    @property
    def _timeout_config(self):
        timeout_config = {}
        if self._config.pdp_timeout is not None:
            timeout_config["timeout"] = ClientTimeout(total=self._config.pdp_timeout)
        return timeout_config

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
        normalized_resource: ResourceInput = self._normalize_resource(
            (
                self._resource_from_string(resource)
                if isinstance(resource, str)
                else ResourceInput(**resource)
            )
        )
        query_context = self._context_store.get_derived_context(context)
        input = dict(
            action=action,
            resource=normalized_resource.dict(exclude_unset=True),
            context=query_context,
        )

        async with aiohttp.ClientSession(
            headers=self._headers, **self._timeout_config
        ) as session:
            check_url = f"{self._base_url}/authorized_users"
            try:
                async with session.post(
                    check_url,
                    data=json.dumps(input),
                ) as response:
                    if response.status != 200:
                        if response.status == 501:
                            raise PermitConnectionError(
                                f"Permit SDK got an error: {response.status},\n"
                                "and cannot connect to the PDP container. Please ensure you are not using ABAC/ReBAC policies,\n"
                                "as the cloud PDP is not compatible with these kinds of policies.\n"
                                "Also, please check your configuration and make sure it's running at {self._base_url} and accepting requests.\n"
                                "Read more about setting up the PDP at "
                                "https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                            )

                        error_json: dict = await response.json()
                        logger.error(
                            "error in permit.authorized_users({}, {}):\n{}\n{}".format(
                                action,
                                self._resource_repr(normalized_resource),
                                f"status code: {response.status}",
                                repr(error_json),
                            )
                        )
                        raise PermitConnectionError(
                            f"Permit SDK got unexpected status code: {response.status}, please check your Permit SDK class init and PDP container are configured correctly. \n\
                            Read more about setting up the PDP at https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                        )

                    content: dict = await response.json()
                    logger.debug(
                        f"permit.authorized_users() response:\ninput: {pformat(input, indent=2)}\nresponse status: {response.status}\nresponse data: {pformat(content, indent=2)}"
                    )
                    result: AuthorizedUsersResult = parse_obj_as(
                        AuthorizedUsersResult, content
                    )
                    return result
            except aiohttp.ClientError as err:
                logger.error(
                    "error in permit.authorized_users({}, {}):\n{}".format(
                        action,
                        self._resource_repr(normalized_resource),
                        err,
                    )
                )
                raise PermitConnectionError(
                    f"Permit SDK got error: {err}, \n \
                    and cannot connect to the PDP container, please check your configuration and make sure it's running at {self._base_url} and accepting requests. \n \
                    Read more about setting up the PDP at https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                )

    async def bulk_check(
        self,
        checks: list[CheckQuery],
        context: Context = {},
    ) -> list[bool]:
        """
        Checks if a user is authorized to perform an action on a resource within the specified context.

        Args:
            checks: A list of CheckQuery objects representing the authorization queries to be performed.
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

        input = []
        for check in checks:
            normalized_user: UserInput = (
                UserInput(key=check["user"])
                if isinstance(check["user"], str)
                else UserInput(**check["user"])
            )
            normalized_resource: ResourceInput = self._normalize_resource(
                (
                    self._resource_from_string(check["resource"])
                    if isinstance(check["resource"], str)
                    else ResourceInput(**check["resource"])
                )
            )
            query_context = self._context_store.get_derived_context(context)
            input.append(
                dict(
                    user=normalized_user.dict(exclude_unset=True),
                    action=check["action"],
                    resource=normalized_resource.dict(exclude_unset=True),
                    context=query_context,
                )
            )

        async with aiohttp.ClientSession(
            headers=self._headers, **self._timeout_config
        ) as session:
            check_url = f"{self._base_url}/allowed/bulk"
            try:
                async with session.post(
                    check_url,
                    data=json.dumps(input),
                ) as response:
                    if response.status != 200:
                        error_json: dict = await response.json()
                        logger.error(
                            "error in permit.check({}):\n{}\n{}".format(
                                (
                                    [
                                        [
                                            check.get("user"),
                                            check.get("action"),
                                            check.get("resource"),
                                        ]
                                        for check in input
                                    ]
                                ),
                                f"status code: {response.status}",
                                repr(error_json),
                            )
                        )
                        raise PermitConnectionError
                    content: dict = await response.json()
                    logger.debug(
                        f"permit.check() response:\ninput: {pformat(input, indent=2)}\nresponse status: {response.status}\nresponse data: {pformat(content, indent=2)}"
                    )
                    data = content.get(
                        "allow", content.get("result", {}).get("allow", [])
                    )
                    decisions: list[bool] = [
                        bool(item.get("allow", False)) for item in data
                    ]
            except aiohttp.ClientError as err:
                logger.error(
                    "error in permit.check({}):\n{}".format(
                        (
                            [
                                [
                                    check.get("user"),
                                    check.get("action"),
                                    check.get("resource"),
                                ]
                                for check in input
                            ]
                        ),
                        err,
                    )
                )
                raise PermitConnectionError
            return decisions

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

        normalized_user: UserInput = (
            UserInput(key=user) if isinstance(user, str) else UserInput(**user)
        )
        normalized_resource: ResourceInput = self._normalize_resource(
            (
                self._resource_from_string(resource)
                if isinstance(resource, str)
                else ResourceInput(**resource)
            )
        )
        query_context = self._context_store.get_derived_context(context)
        input = dict(
            user=normalized_user.dict(exclude_unset=True),
            action=action,
            resource=normalized_resource.dict(exclude_unset=True),
            context=query_context,
        )
        async with aiohttp.ClientSession(
            headers=self._headers, **self._timeout_config
        ) as session:
            check_url = f"{self._base_url}/allowed"
            try:
                async with session.post(
                    check_url,
                    data=json.dumps(input),
                ) as response:
                    if response.status != 200:
                        if response.status == 501:
                            raise PermitConnectionError(
                                f"Permit SDK got an error: {response.status},\n"
                                "and cannot connect to the PDP container. Please ensure you are not using ABAC/ReBAC policies,\n"
                                "as the cloud PDP is not compatible with these kinds of policies.\n"
                                "Also, please check your configuration and make sure it's running at {self._base_url} and accepting requests.\n"
                                "Read more about setting up the PDP at "
                                "https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                            )

                        error_json: dict = await response.json()
                        logger.error(
                            "error in permit.check({}, {}, {}):\n{}\n{}".format(
                                normalized_user,
                                action,
                                self._resource_repr(normalized_resource),
                                f"status code: {response.status}",
                                repr(error_json),
                            )
                        )
                        raise PermitConnectionError(
                            f"Permit SDK got unexpected status code: {response.status}, please check your Permit SDK class init and PDP container are configured correctly. \n\
                            Read more about setting up the PDP at https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                        )

                    content: dict = await response.json()
                    logger.debug(
                        f"permit.check() response:\ninput: {pformat(input, indent=2)}\nresponse status: {response.status}\nresponse data: {pformat(content, indent=2)}"
                    )
                    decision: bool = bool(content.get("allow", False))
                    # TODO: restore simple log when PDP is fixed
                    # logger.debug(
                    #     "permit.check({}, {}, {}) = {}".format(
                    #         normalized_user,
                    #         action,
                    #         self._resource_repr(normalized_resource),
                    #         repr(decision),
                    #     )
                    # )
                    return decision
            except aiohttp.ClientError as err:
                logger.error(
                    "error in permit.check({}, {}, {}):\n{}".format(
                        normalized_user,
                        action,
                        self._resource_repr(normalized_resource),
                        err,
                    )
                )
                raise PermitConnectionError(
                    f"Permit SDK got error: {err}, \n \
                    and cannot connect to the PDP container, please check your configuration and make sure it's running at {self._base_url} and accepting requests. \n \
                    Read more about setting up the PDP at https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                )

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
        normalized_user: UserInput = (
            UserInput(key=user) if isinstance(user, str) else UserInput(**user)
        )
        normalized_resource: ResourceInput = self._normalize_resource(
            self._resource_from_string(resource_type)
        )
        query_context = self._context_store.get_derived_context(context)
        input = dict(
            user=normalized_user.dict(exclude_unset=True),
            action=action,
            resource=normalized_resource.dict(exclude_unset=True),
            context=query_context,
        )
        async with aiohttp.ClientSession(
            headers=self._headers, **self._timeout_config
        ) as session:
            api_url = f"{self._base_url}/filter_resources"
            try:
                async with session.post(
                    api_url,
                    data=json.dumps(input),
                ) as response:
                    if response.status != 200:
                        raise PermitConnectionError(
                            f"Permit SDK got unexpected status code: {response.status}, please check your Permit SDK class init and PDP container are configured correctly. \n\
                            Read more about setting up the PDP at https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                        )

                    response_data: dict = await response.json()
                    logger.debug(
                        f"permit.filter_resources() response:\ninput: {pformat(input, indent=2)}\nresponse status: {response.status}\nresponse data: {pformat(response_data, indent=2)}"
                    )
                    return ResidualPolicyResponse(**response_data)
            except aiohttp.ClientError as err:
                logger.error(
                    "error in permit.filter_resources({}, {}, {}):\n{}".format(
                        normalized_user,
                        action,
                        self._resource_repr(normalized_resource),
                        err,
                    )
                )
                raise PermitConnectionError(
                    f"Permit SDK got error: {err}, \n \
                    and cannot connect to the PDP container, please check your configuration and make sure it's running at {self._base_url} and accepting requests. \n \
                    Read more about setting up the PDP at https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"
                )

    def _normalize_resource(self, resource: ResourceInput) -> ResourceInput:
        normalized_resource: ResourceInput = resource.copy()
        if normalized_resource.context is None:
            normalized_resource.context = {}

        # if tenant is empty, we migth auto-set the default tenant according to config
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
        if len(parts) < 1 or len(parts) > 2:
            raise ValueError(f"permit.check() got invalid resource string: {resource}")
        return ResourceInput(type=parts[0], key=(parts[1] if len(parts) > 1 else None))


class SyncEnforcer(Enforcer, metaclass=SyncClass):
    pass
