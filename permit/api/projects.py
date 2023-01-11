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
        """
        Lists the projects that you own - based on your Permit.io client's token.
        You can use organization-level API key to list all projects under your organization, otherwise,
        only one project will be returned - the project of the API key.

        Usage Example:
            ```
            from permit import Permit, ProjectRead
            permit = Permit(...)
            projects: List[ProjectRead] = await permit.api.projects.list()
            ```
        """
        projects = await list_projects.asyncio(
            page=page,
            per_page=per_page,
            client=self._client,
        )
        raise_for_error_by_action(projects, "list", "projects")
        return projects

    @lazy_load_context
    async def get(self, project_key: str) -> ProjectRead:
        """
        Gets a project for a given project key.
        In the case that you have a project set in your context,
        or if you are using an environment/project-level API key, only the chosen project is obtainable.

        Usage Example:
            ```
            from permit import Permit, ProjectRead
            permit = Permit(...)
            project: ProjectRead = await permit.api.projects.get("proj")
            ```
        """
        project = await get_project.asyncio(
            project_key,
            client=self._client,
        )
        raise_for_error_by_action(project, "project", project_key)
        return project

    @lazy_load_context
    async def get_by_key(self, project_key: str) -> ProjectRead:
        """
        Gets a project for a given project key - same as `get()` function.
        In the case that you have a project set in your context,
        or if you are using an environment/project-level API key, only the chosen project is obtainable.

        Usage Example:
            ```
            from permit import Permit, ProjectRead
            permit = Permit(...)
            project: ProjectRead = await permit.api.projects.get_by_key("proj")
            ```
        """
        return await self.get(project_key)

    @lazy_load_context
    async def get_by_id(self, project_id: UUID) -> ProjectRead:
        """
        Gets a project for a given project id.
        In the case that you have a project set in your context,
        or if you are using an environment/project-level API key, only the chosen project is obtainable.

        Usage Example:
            ```
            from permit import Permit, ProjectRead
            permit = Permit(...)
            project: ProjectRead = await permit.api.projects.get_by_id(UUID("ed4b285d-3539-4a4d-b8d9-2a3f85d7e438"))
            ```
        """
        return await self.get(project_id.hex)

    @lazy_load_context
    async def create(self, project: Union[ProjectCreate, dict]) -> ProjectRead:
        """
        Creates a project under the context's organization - can be either ProjectCreate or a dictionary.
        You can create a new project only if you are using an organization-level API key.

        Usage Example:
            ```
            from permit import Permit, ProjectRead, ProjectCreate
            permit = Permit(...)
            project_create = ProjectCreate(
                key="proj-x",
                name="Project X",
                description="Our Project-X project", settings={}
            )
            project: ProjectRead = await permit.api.projects.create(project_create)
            ```
        """
        ProjectCreate(key="asdf.!24$%^&ד")
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
        """
        Updates a project under the context's organization - given a project key -
        can be either ProjectUpdate or a dictionary.
        In the case that you have an environment set in your context, you can't update projects.
        If you are using a project-level API key, only the context's project is mutable.

        Usage Example:
            ```
            from permit import Permit, ProjectRead, ProjectUpdate
            permit = Permit(...)
            project_update = ProjectUpdate(
                name="Project XY",
                description="Our Project-XY project", settings={}
            )
            project: ProjectRead = await permit.api.projects.update("proj-x", project_update)
            ```
        """
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
        """
        Deletes a project under the context's organization - given a project key.
        In the case that you have an environment set in your context, you can't delete a project.
        If you are using a project-level API key, only the context's project can be deleted.

        Usage Example:
            ```
            from permit import Permit
            permit = Permit(...)
            await permit.api.projects.delete("proj-x")
            ```
        """
        res = await delete_project.asyncio(
            project_key,
            client=self._client,
        )
        raise_for_error_by_action(res, "project", project_key, "delete")
