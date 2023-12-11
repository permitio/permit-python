import json
from pprint import pformat
from typing import Union

import aiohttp
from loguru import logger

from ..config import PermitConfig
from ..exceptions import PermitConnectionError
from ..utils.context import Context, ContextStore
from ..utils.sync import SyncClass
from .interfaces import ResourceInput, UserInput


def set_if_not_none(d: dict, k: str, v):
    if v is not None:
        d[k] = v


RESOURCE_DELIMITER = ":"

User = Union[dict, str]
Action = str
Resource = Union[dict, str]


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

        async with aiohttp.ClientSession(headers=self._headers) as session:
            check_url = f"{self._base_url}/allowed"
            try:
                async with session.post(
                    check_url,
                    data=json.dumps(input),
                ) as response:
                    if response.status != 200:
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
                            Read more about setting up the PDP at https://docs.permit.io/reference/SDKs/Python/quickstart_python"
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
                    Read more about setting up the PDP at https://docs.permit.io/reference/SDKs/Python/quickstart_python"
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
