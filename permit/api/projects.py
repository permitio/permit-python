from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

from permit.api.base import PermitBaseApi, lazy_load_context
from permit.config import PermitConfig
from permit.exceptions.exceptions import raise_for_error_by_action
from permit.openapi.api.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from permit.openapi.models import ProjectCreate, ProjectRead, ProjectUpdate

if TYPE_CHECKING:
    from loguru import Logger


class Project(PermitBaseApi):
    def __init__(
        self,
        client,
        config: PermitConfig,

        logger: Logger,
    ):
        super().__init__(client=client, config=config, logger=logger)

    # CRUD Methods
    @lazy_load_context
    async def list(self, page: int = 1, per_page: int = 100) -> List[ProjectRead]:
        projects = await list_projects.asyncio(
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(projects, "list", "projects")
        return projects

    @lazy_load_context
    async def get(self, project_key: str) -> ProjectRead:
        project = await get_project.asyncio(
            project_key,
            client=self._client,
        )
        raise_for_error_by_action(project, "project", project_key)
        return project

    @lazy_load_context
    async def get_by_key(self, project_key: str) -> ProjectRead:
        return await self.get(project_key)

    @lazy_load_context
    async def get_by_id(self, project_id: UUID) -> ProjectRead:
        return await self.get(project_id.hex)

    @lazy_load_context
    async def create(self, project: Union[ProjectCreate, dict]) -> ProjectRead:
        if isinstance(project, dict):
            json_body = ProjectCreate.parse_obj(project)
        else:
            json_body = project
        project = await create_project.asyncio(
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            project, "project", json.dumps(json_body.dict()), "create"
        )
        return project

    @lazy_load_context
    async def update(
        self, project_key: str, project: Union[ProjectUpdate, dict]
    ) -> ProjectRead:
        if isinstance(project, dict):
            json_body = ProjectUpdate.parse_obj(project)
        else:
            json_body = project
        updated_project = await update_project.asyncio(
            project_key,
            json_body=json_body,
            client=self._client,
        )
        raise_for_error_by_action(
            project, "project", json.dumps(json_body.dict()), "update"
        )
        return updated_project

    @lazy_load_context
    async def delete(self, project_key: str):
        res = await delete_project.asyncio(
            project_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "project", project_key, "delete")
