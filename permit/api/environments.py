from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from loguru import Logger

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.environments import (
    create_environment,
    delete_environment,
    get_environment,
    list_environments,
    update_environment,
)
from permit.openapi.models import EnvironmentCreate, EnvironmentRead, EnvironmentUpdate


class Environment(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,
        logger: Logger,
    ):
        super().__init__(client=client, config=config, logger=logger)

    # CRUD Methods
    @lazy_load_context
    async def list(self, page: int = 1, per_page: int = 100) -> List[EnvironmentRead]:
        """
        Lists the environments that you own - based on your Permit.io client's token.
        You can use organization/project-level API key to list all environments under your project, otherwise,
        only one environment will be returned - the environment of the API key.

        Usage Example:
            ```
            from permit import Permit, EnvironmentRead
            permit = Permit(...)
            environments: List[EnvironmentRead] = await permit.api.environments.list()
            ```
        """
        environments = await list_environments.asyncio(
            self._config.context.project,
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(environments, "list", "environments")
        return environments

    @lazy_load_context
    async def get(self, environment_key: str) -> EnvironmentRead:
        """
        Gets an environment for a given environment key.
        In the case that you have an environment set in your context,
        or if you are using an environment-level API key, only the chosen environment is obtainable.

        Usage Example:
            ```
            from permit import Permit, EnvironmentRead
            permit = Permit(...)
            environment: EnvironmentRead = await permit.api.environments.get("development")
            ```
        """
        environment = await get_environment.asyncio(
            self._config.context.project,
            environment_key,
            client=self._client,
        )
        raise_for_error_by_action(environment, "environment", environment_key)
        return environment

    @lazy_load_context
    async def get_by_key(self, environment_key: str) -> EnvironmentRead:
        """
        Gets an environment for a given environment key - same as `get()` function.
        In the case that you have an environment set in your context,
        or if you are using an environment-level API key, only the chosen environment is obtainable.

        Usage Example:
            ```
            from permit import Permit, EnvironmentRead
            permit = Permit(...)
            environment: EnvironmentRead = await permit.api.environments.get_by_key("development")
            ```
        """
        return await self.get(environment_key)

    @lazy_load_context
    async def get_by_id(self, environment_id: UUID) -> EnvironmentRead:
        """
        Gets an environment for a given environment id.
        In the case that you have an environment set in your context,
        or if you are using an environment-level API key, only the chosen environment is obtainable.

        Usage Example:
            ```
            from permit import Permit, EnvironmentRead
            permit = Permit(...)
            environment: EnvironmentRead = await permit.api.environments.get_by_id(UUID("37f8c4c7-676f-47e9-b1e1-b213ffca475f"))
            ```
        """
        return await self.get(environment_id.hex)

    @lazy_load_context
    async def create(
        self, environment: Union[EnvironmentCreate, dict]
    ) -> EnvironmentRead:
        """
        Creates an environment under the context's project - can be either EnvironmentCreate or a dictionary.
        You can create a new environment only if you are using a project/organization-level API key.

        Usage Example:
            ```
            from permit import Permit, EnvironmentRead, EnvironmentCreate
            permit = Permit(...)
            environment_create = EnvironmentCreate(
                key="staging",
                name="Staging",
                description="Our staging environment"
            )
            environment: EnvironmentRead = await permit.api.environments.create(environment_create)
            ```
        """

        if isinstance(environment, dict):
            json_body = EnvironmentCreate.parse_obj(environment)
        else:
            json_body = environment
        environment = await create_environment.asyncio(
            self._config.context.project,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            environment, "environment", json.dumps(json_body.dict()), "create"
        )
        return environment

    @lazy_load_context
    async def update(
        self, environment_key: str, environment: Union[EnvironmentUpdate, dict]
    ) -> EnvironmentRead:
        """
        Updates an environment under the context's project - given an environment key -
        can be either EnvironmentUpdate or a dictionary.
        In the case that you have an environment set in your context,
        or if you are using an environment-level API key, only the context's environment is mutable.

        Usage Example:
            ```
            from permit import Permit, EnvironmentRead, EnvironmentUpdate
            permit = Permit(...)
            environment_update = EnvironmentUpdate(
                name="Staging-old",
                description="Our old staging environment"
            )
            environment: EnvironmentRead = await permit.api.environments.update("staging", environment_create)
            ```
        """
        if isinstance(environment, dict):
            json_body = EnvironmentUpdate.parse_obj(environment)
        else:
            json_body = environment
        updated_environment = await update_environment.asyncio(
            self._config.context.project,
            environment_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            environment, "environment", json.dumps(json_body.dict()), "update"
        )
        return updated_environment

    @lazy_load_context
    async def delete(self, environment_key: str):
        """
        Deletes an environment under the context's project - given an environment key.
        In the case that you have an environment set in your context,
        or if you are using an environment-level API key, only the context's environment can be deleted.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.environments.delete("staging")
            ```
        """
        res = await delete_environment.asyncio(
            self._config.context.project,
            environment_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "environment", environment_key, "delete")
