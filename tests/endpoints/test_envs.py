import os
from typing import List

import pytest
from loguru import logger

from permit import Permit
from permit.api.context import ApiKeyLevel
from permit.api.models import (
    EnvironmentCreate,
    EnvironmentRead,
    ProjectCreate,
    ProjectRead,
)
from permit.config import PermitConfig
from permit.exceptions import PermitApiError, PermitConnectionError, PermitContextError
from tests.utils import handle_api_error

CREATED_PROJECTS = [ProjectCreate(key="test-python-proj", name="New Python Project")]
CREATED_ENVIRONMENTS = [
    EnvironmentCreate(key="my-python-env", name="My Python Env"),
    EnvironmentCreate(key="my-python-env-2", name="My Python Env 2"),
]


@pytest.fixture
def permit_with_org_level_api_key() -> Permit:
    token = os.getenv("ORG_PDP_API_KEY", "")
    pdp_address = os.getenv("PDP_URL", "http://localhost:7766")
    api_url = os.getenv("PDP_CONTROL_PLANE", "https://api.permit.io")

    return Permit(
        PermitConfig(
            **{
                "token": token,
                "pdp": pdp_address,
                "api_url": api_url,
                "log": {
                    "level": "debug",
                    "enable": True,
                },
            }
        )
    )


@pytest.fixture
def permit_with_project_level_api_key() -> Permit:
    token = os.getenv("PROJECT_PDP_API_KEY", "")
    pdp_address = os.getenv("PDP_URL", "http://localhost:7766")
    api_url = os.getenv("PDP_CONTROL_PLANE", "https://api.permit.io")

    return Permit(
        PermitConfig(
            **{
                "token": token,
                "pdp": pdp_address,
                "api_url": api_url,
                "log": {
                    "level": "debug",
                    "enable": True,
                },
            }
        )
    )


async def cleanup(permit: Permit, project_key: str):
    for env in CREATED_ENVIRONMENTS:
        try:
            await permit.api.environments.delete(project_key, env.key)
        except PermitApiError as error:
            if error.status_code == 404:
                print(
                    f"SKIPPING delete, env does not exist: {env.key}, project_key={project_key}"
                )


async def test_environment_creation_with_org_level_api_key(
    permit_with_org_level_api_key: Permit,
):
    permit = permit_with_org_level_api_key
    try:
        await permit.api._ensure_context(ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY)
    except PermitContextError:
        logger.warning("this test must run with an org level api key")
        return

    try:
        await cleanup(permit, CREATED_PROJECTS[0].key)
        projects: List[ProjectRead] = []
        for project_data in CREATED_PROJECTS:
            print(f"trying to creating project: {project_data.key}")
            try:
                project: ProjectRead = await permit.api.projects.create(project_data)
            except PermitApiError as error:
                if error.status_code == 409:
                    print(
                        f"SKIPPING create, project already exists: {project_data.key}"
                    )
                project: ProjectRead = await permit.api.projects.get(
                    project_key=project_data.key
                )
            assert project is not None
            assert project.key == project_data.key
            assert project.name == project_data.name
            assert project.description == project_data.description
            projects.append(project)

        # create environments
        for environment_data in CREATED_ENVIRONMENTS:
            print(f"creating environment: {environment_data.key}")
            environment: EnvironmentRead = await permit.api.environments.create(
                project_key=project.key, environment_data=environment_data
            )
            assert environment is not None
            assert environment.key == environment_data.key
            assert environment.name == environment_data.name
            assert environment.description == environment_data.description
            assert environment.project_id == projects[0].id

        # initial number of items
        environments = await permit.api.environments.list(project_key=projects[0].key)
        assert len(CREATED_ENVIRONMENTS) + 2 == len(
            environments
        )  # each project has 2 default `dev` and `prod` environments

        # create first item
        test_environment = await permit.api.environments.get(
            CREATED_PROJECTS[0].key, CREATED_ENVIRONMENTS[0].key
        )

        assert test_environment is not None
        assert test_environment.key == CREATED_ENVIRONMENTS[0].key
        assert test_environment.name == CREATED_ENVIRONMENTS[0].name
        assert test_environment.description == CREATED_ENVIRONMENTS[0].description
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError as error:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        await cleanup(permit, CREATED_PROJECTS[0].key)


async def test_environment_creation_with_project_level_api_key(
    permit_with_project_level_api_key: Permit,
):
    permit = permit_with_project_level_api_key
    try:
        await permit.api._ensure_context(ApiKeyLevel.PROJECT_LEVEL_API_KEY)
    except PermitContextError:
        logger.warning("this test must run with a project level api key")
        return

    try:
        project = permit.config.api_context.project
        assert project is not None
        project_id = str(project)

        project = await permit.api.projects.get(project_id)
        assert str(project.id) == project_id

        await cleanup(permit, project.key)

        # create environments
        for environment_data in CREATED_ENVIRONMENTS:
            print(f"creating environment: {environment_data.key}")
            environment: EnvironmentRead = await permit.api.environments.create(
                project_key=project.key, environment_data=environment_data
            )
            assert environment is not None
            assert environment.key == environment_data.key
            assert environment.name == environment_data.name
            assert environment.description == environment_data.description
            assert environment.project_id == project.id

        # initial number of items
        environments = await permit.api.environments.list(project_key=project.key)
        actual_env_set = {env.key for env in environments}
        created_env_set = {env.key for env in CREATED_ENVIRONMENTS}
        assert len(actual_env_set.intersection(created_env_set)) == 2
    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError as error:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        await cleanup(permit, project.key)
