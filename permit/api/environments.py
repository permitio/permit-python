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
        environment = await get_environment.asyncio(
            self._config.context.project,
            environment_key,
            client=self._client,
        )
        raise_for_error_by_action(environment, "environment", environment_key)
        return environment

    @lazy_load_context
    async def get_by_key(self, environment_key: str) -> EnvironmentRead:
        return await self.get(environment_key)

    @lazy_load_context
    async def get_by_id(self, environment_id: UUID) -> EnvironmentRead:
        return await self.get(environment_id.hex)

    @lazy_load_context
    async def create(
        self, environment: Union[EnvironmentCreate, dict]
    ) -> EnvironmentRead:
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
        res = await delete_environment.asyncio(
            self._config.context.project,
            environment_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "environment", environment_key, "delete")
