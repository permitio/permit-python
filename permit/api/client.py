from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, Generic, List, Optional, TypeVar, Union

from loguru import logger
from typing_extensions import ParamSpec

from permit.api.base import lazy_load_context
from permit.api.elements import Elements
from permit.api.environments import Environment
from permit.api.projects import Project
from permit.api.resource_actions import ResourceAction
from permit.api.resource_attributes import ResourceAttribute
from permit.api.resources import Resource
from permit.api.roles import Role
from permit.api.tenants import Tenant
from permit.api.users import User
from permit.config import PermitConfig, PermitContext, ContextFactory
from permit.constants import (
    DEPRECATION_WARNING_LOG,
    OBJECT_ENVIRONMENT_NAME,
    OBJECT_PROJECT_NAME,
    OBJECT_TENANT_NAME, DEFAULT_TENANT_KEY,
)
from permit.openapi import AuthenticatedClient
from permit.openapi.models import (
    ResourceRead,
    RoleAssignmentRead,
    RoleRead,
    TenantRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from permit.resources.interfaces import OnUserCreation

T = TypeVar("T")

AsyncCallback = Callable[[], Awaitable[Dict]]


class Operation(Generic[T]):
    def __init__(self, callback: AsyncCallback):
        self._callback = callback

    async def run(self) -> T:
        return await self._callback()


class ReadOperation(Operation[Dict]):
    pass


class WriteOperation(Operation[Dict]):
    pass


P = ParamSpec("P")
RT = TypeVar("RT")


class PermitApiClient:
    def __init__(self, config: PermitConfig):
        self._config = config
        self._logger = logger.bind(name="permit.mutations.client")

        self.client = AuthenticatedClient(base_url=config.api_url, token=config.token)
        self.tenants: Tenant = Tenant(self.client, self._config, self._logger)
        self.environments: Environment = Environment(
            self.client, self._config, self._logger
        )
        self.projects: Project = Project(self.client, self._config, self._logger)
        self.resource_actions: ResourceAction = ResourceAction(
            self.client, self._config, self._logger
        )
        self.resource_attributes: ResourceAttribute = ResourceAttribute(
            self.client, self._config, self._logger
        )
        self.resources: Resource = Resource(
            self.client,
            self._config,
            self._logger,
            self.resource_attributes,
            self.resource_actions,
        )
        self.roles: Role = Role(self.client, self._config, self._logger)
        self.users: User = User(self.client, self._config, self._logger)
        self.elements: Elements = Elements(self.client, self._config, self._logger)

    # region read api ----------------------------------------------------------------

    @lazy_load_context
    async def get_user(self, user_key: str) -> UserRead:
        # DEPRECATED ! Please use the API level method - instead of `permit.get_user()` use `permit.api.users.get()`.
        self._logger.warning(
            DEPRECATION_WARNING_LOG.format(
                "permit.get_user()", "permit.api.users.get()"
            )
        )
        return await self.users.get(user_key)

    @lazy_load_context
    async def get_role(self, role_key: str) -> RoleRead:
        # DEPRECATED ! Please use the API level method - instead of `permit.get_role()` use `permit.api.roles.get()`.
        self._logger.warning(
            DEPRECATION_WARNING_LOG.format(
                "permit.get_role()", "permit.api.roles.get()"
            )
        )
        return await self.roles.get(role_key)

    @lazy_load_context
    async def get_tenant(self, tenant_key: str) -> TenantRead:
        # DEPRECATED ! Please use the API level method - instead of `permit.get_tenant()` use
        # `permit.api.tenants.get()`.
        self._logger.warning(
            DEPRECATION_WARNING_LOG.format(
                "permit.get_tenant()", "permit.api.tenants.get()"
            )
        )
        return await self.tenants.get(tenant_key)

    @lazy_load_context
    async def get_assigned_roles(
        self,
        user_key: str,
        tenant_key: Optional[str],
        page: int = 1,
        per_page: int = 100,
    ) -> List[RoleAssignmentRead]:
        # DEPRECATED ! Please use the API level method - instead of `permit.get_assigned_roles()` use
        # `permit.api.users.get_assigned_roles()`.
        self._logger.warning(
            DEPRECATION_WARNING_LOG.format(
                "permit.get_assigned_roles()", "permit.api.users.get_assigned_roles()"
            )
        )
        return await self.users.get_assigned_roles(user_key, tenant_key, page, per_page)

    @lazy_load_context
    async def get_resource(self, resource_key: str) -> ResourceRead:
        # DEPRECATED ! Please use the API level method - instead of `permit.get_resource()` use
        # `permit.api.resources.get()`.
        self._logger.warning(
            DEPRECATION_WARNING_LOG.format(
                "permit.get_resource()", "permit.api.resources.get()"
            )
        )
        return await self.resources.get(resource_key)

    # region write api ---------------------------------------------------------------
    async def _is_context_valid(self) -> None:
        context = self._config.context
        if self._config.context.project:
            await self.projects.get(context.project)
        if self._config.context.environment:
            await self.environments.get(context.environment)
        if self._config.context.project:
            await self.tenants.get(context.tenant)

    async def set_context(self, context: PermitContext | dict) -> None:
        log_message = "Setting context - "
        additional_log_text = "{}: {}"
        if isinstance(context, dict):
            context = PermitContext(**context)
        if context.project:
            log_message += additional_log_text.format(OBJECT_PROJECT_NAME, context.project)
        if context.environment:
            log_message += additional_log_text.format(OBJECT_ENVIRONMENT_NAME, context.environment)
        if context.tenant:
            log_message += additional_log_text.format(OBJECT_TENANT_NAME, context.tenant)

        self._logger.info(log_message)
        self._config.context = await ContextFactory.build(self.client, context.project, context.environment,
                                                          context.tenant or DEFAULT_TENANT_KEY, is_user_input=True)
        await self._is_context_valid()

    @lazy_load_context
    async def sync_user(
        self, user: Union[UserCreate, dict], on_create: OnUserCreation = None
    ) -> UserRead:
        if isinstance(user, dict):
            key = user.get("key", None)
            if key is None:
                raise KeyError("required 'key' in input dictionary")
        else:
            key = user.key
        # check if the user key already exists
        self._logger.info(f"checking if user '{key}' already exists")
        try:
            user_to_update = await self.users.get(key)
        except:
            user_to_update = None

        if user_to_update is not None:
            self._logger.info("user exists, updating it...")
            # if the user exists update it
            if isinstance(user, dict):
                user_update = UserUpdate.parse_obj(user)
            else:
                user_update = UserUpdate.parse_obj(user.dict(exclude={"key"}))
            updated_user = await self.users.update(key, user_update)
            return updated_user
        # otherwise create the user
        self._logger.info("user does not exist, creating it...")
        created_user = await self.users.create(user)

        # Set initial roles when new user is created

        for initial_role in on_create.initial_roles:
            await self.users.assign_role(
                key, initial_role.role, initial_role.tenant
            )


        return created_user

    # endregion
    # region cloud api proxy ---------------------------------------------------------
    @staticmethod
    async def read(*operations: ReadOperation) -> List[Dict]:
        # reads do not need to be resolved in order, can be in parallel
        return list(await asyncio.gather(*(op.run() for op in operations)))

    @staticmethod
    async def write(*operations: WriteOperation) -> List[Dict]:
        # writes must be in order
        results = []
        for op in operations:
            result = await op.run()
            results.append(result)
        return results

    # endregion
