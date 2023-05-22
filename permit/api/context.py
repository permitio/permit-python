from enum import Enum
from typing import Optional


class ApiKeyLevel(str, Enum):
    """
    The `ApiKeyLevel` enum represents the levels of API key authorization in Permit.
    """

    WAIT_FOR_INIT = "WAIT_FOR_INIT"
    """
    Wait for initialization of the API key.
    """

    ORGANIZATION_LEVEL_API_KEY = "ORGANIZATION_LEVEL_API_KEY"
    """
    Organization level API key authorization.
    Using an API key of this scope will allow the SDK user to modify
    all projects and environments under the organization / workspace.
    """

    PROJECT_LEVEL_API_KEY = "PROJECT_LEVEL_API_KEY"
    """
    Project level API key authorization.
    Using an API key of this scope will allow the SDK user to modify
    a single project and the environments under that project.
    """

    ENVIRONMENT_LEVEL_API_KEY = "ENVIRONMENT_LEVEL_API_KEY"
    """
    Environment level API key authorization.
    Using an API key of this scope will allow the SDK user to modify
    a single Permit environment.
    """


class ApiContext:
    """
    The `ApiContext` class represents the context for API key authorization in Permit.
    It allows setting and retrieving the API Key context to be either:
    organization-level context, project-level context, or environment-level context.
    """

    def __init__(self):
        self._level = ApiKeyLevel.WAIT_FOR_INIT
        self._organization = None
        self._project = None
        self._environment = None

    @property
    def level(self) -> ApiKeyLevel:
        """
        Get the current API key level.

        Returns:
            The current API key level.
        """
        return self._level

    @property
    def organization(self) -> Optional[str]:
        """
        Get the current organization in the context.

        Returns:
            The current organization in the context.
        """
        return self._organization

    @property
    def project(self) -> Optional[str]:
        """
        Get the current project in the context.

        Returns:
            The current project in the context.
        """
        return self._project

    @property
    def environment(self) -> Optional[str]:
        """
        Get the current environment in the context.

        Returns:
            The current environment in the context.
        """
        return self._environment

    def set_organization_level_context(self, org: str):
        """
        Set the context to organization level.

        Args:
            org: The organization key.
        """
        self._level = ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY
        self._organization = org
        self._project = None
        self._environment = None

    def set_project_level_context(self, org: str, project: str):
        """
        Set the context to project level.

        Args:
            org: The organization key.
            project: The project key.
        """
        self._level = ApiKeyLevel.PROJECT_LEVEL_API_KEY
        self._organization = org
        self._project = project
        self._environment = None

    def set_environment_level_context(self, org: str, project: str, environment: str):
        """
        Set the context to environment level.

        Args:
            org: The organization key.
            project: The project key.
            environment: The environment key.
        """
        self._level = ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY
        self._organization = org
        self._project = project
        self._environment = environment
