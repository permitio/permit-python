from enum import Enum
from typing import Optional

from loguru import logger

from ..exceptions import PermitContextChangeError


class ApiKeyAccessLevel(str, Enum):
    """
    The `ApiKeyAccessLevel` enum represents the access level of a Permit API Key.
    """

    WAIT_FOR_INIT = "WAIT_FOR_INIT"
    """
    Wait for initialization of the API key.
    """

    ORGANIZATION_LEVEL_API_KEY = "ORGANIZATION_LEVEL_API_KEY"
    """
    This type of API Key will allow the SDK user to modify all projects and
    environments under the granted organization (workspace).
    """

    PROJECT_LEVEL_API_KEY = "PROJECT_LEVEL_API_KEY"
    """
    This type of API Key will allow the SDK user to modify
    a single project and the environments under that project.
    """

    ENVIRONMENT_LEVEL_API_KEY = "ENVIRONMENT_LEVEL_API_KEY"
    """
    This type of API Key will allow the SDK user to modify a single Permit environment.
    """


API_ACCESS_LEVELS = [
    ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY,
    ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY,
    ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY,
]


class ApiKeyLevel(str, Enum):
    """
    Deprecated: `ApiKeyLevel` had a confusing name, use `ApiKeyAccessLevel` instead.
    """

    WAIT_FOR_INIT = "WAIT_FOR_INIT"
    ORGANIZATION_LEVEL_API_KEY = "ORGANIZATION_LEVEL_API_KEY"
    PROJECT_LEVEL_API_KEY = "PROJECT_LEVEL_API_KEY"
    ENVIRONMENT_LEVEL_API_KEY = "ENVIRONMENT_LEVEL_API_KEY"


class ApiContextLevel(int, Enum):
    """
    The `ApiContextLevel` enum represents the context level in which the SDK is running.
    """

    WAIT_FOR_INIT = 0
    """
    Signifies that the context is not set yet.
    """

    ORGANIZATION = 1
    """
    When running in this context level, the SDK knows the current organization.
    """

    PROJECT = 2
    """
    When running in this context level, the SDK knows the current organization and project.
    """

    ENVIRONMENT = 3
    """
    When running in this context level, the SDK knows the current organization, project and environment.
    """


class ApiContext:
    """
    The `ApiContext` class represents the required known context for an API method.

    Since the Permit API hierarchy is deeply nested, it is less convenient to specify
    the full object hierarchy in every request.

    For example, in order to list roles, the user need to specify the (id or key) of the:
    - the org
    - the project
    - then environment
    in which the roles are located under.

    Instead, the SDK can "remember" the current context and "auto-complete" the details
    from that context.

    We then get this kind of experience:
    ```
    await permit.api.roles.list()
    ```

    we can only run this function if the current context already knows the org, project
    and environments that we want to run under, and that is why this method assumes
    we are running under a `ApiContextLevel.ENVIRONMENT` context.
    """

    def __init__(self):
        self._permitted_access_level = ApiKeyAccessLevel.WAIT_FOR_INIT
        # org, project and environment the API Key is allowed to access
        self._permitted_organization = None
        self._permitted_project = None
        self._permitted_environment = None

        # current known context
        self._context_level = ApiContextLevel.WAIT_FOR_INIT
        self._organization = None
        self._project = None
        self._environment = None

    def _save_api_key_accessible_scope(
        self, org: str, project: Optional[str] = None, environment: Optional[str] = None
    ):
        """Do not call this method directly!"""
        self._permitted_organization = org  # cannot be none

        if project is not None and environment is not None:
            self._permitted_project = project
            self._permitted_environment = environment
            self._permitted_access_level = ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY
        elif project is not None:
            self._permitted_project = project
            self._permitted_environment = None
            self._permitted_access_level = ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY
        else:
            self._permitted_project = None
            self._permitted_environment = None
            self._permitted_access_level = ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY

    @property
    def permitted_access_level(self) -> ApiKeyAccessLevel:
        """
        Get the current API key level.

        Returns:
            The current API key level.
        """
        return self._permitted_access_level

    @property
    def level(self) -> ApiContextLevel:
        """
        Get the current SDK context level.

        Returns:
            The current SDK context level.
        """
        return self._context_level

    @property
    def organization(self) -> Optional[str]:
        """
        Get the current organization from the SDK context or None if unset.

        Returns:
            The current organization in the context.
        """
        return self._organization

    @property
    def project(self) -> Optional[str]:
        """
        Get the current project from the SDK context or None if unset.

        Returns:
            The current project in the context.
        """
        return self._project

    @property
    def environment(self) -> Optional[str]:
        """
        Get the current environment from the SDK context or None if unset.

        Returns:
            The current environment in the context.
        """
        return self._environment

    def __verify_can_access_org(self, org: str):
        if org != self._permitted_organization:
            raise PermitContextChangeError(
                f"You cannot set an SDK context with org '{org}' due to insufficient API Key permissions"
            )

    def __verify_can_access_project(self, org: str, project: str):
        self.__verify_can_access_org(org)
        if self._permitted_project is not None and project != self._permitted_project:
            raise PermitContextChangeError(
                f"You cannot set an SDK context with project '{project}' due to insufficient API Key permissions"
            )

    def __verify_can_access_environment(self, org: str, project: str, environment: str):
        self.__verify_can_access_project(org, project)
        if (
            self._permitted_environment is not None
            and environment != self._permitted_environment
        ):
            raise PermitContextChangeError(
                f"You cannot set an SDK context with environment '{environment}' due to insufficient API Key permissions"
            )

    def set_organization_level_context(self, org: str):
        """
        Set the current context of the SDK to a specific organization.

        Args:
            org: The organization key.
        """
        self.__verify_can_access_org(org)
        logger.debug(f"Setting organization level context: {org}")
        self._context_level = ApiContextLevel.ORGANIZATION
        self._organization = org
        self._project = None
        self._environment = None

    def set_project_level_context(self, org: str, project: str):
        """
        Set the current context of the SDK to a specific organization and project.

        Args:
            org: The organization key.
            project: The project key.
        """
        self.__verify_can_access_project(org, project)
        logger.debug(f"Setting project level context: {org}/{project}")
        self._context_level = ApiContextLevel.PROJECT
        self._organization = org
        self._project = project
        self._environment = None

    def set_environment_level_context(self, org: str, project: str, environment: str):
        """
        Set the current context of the SDK to a specific organization, project and environment.

        Args:
            org: The organization key.
            project: The project key.
            environment: The environment key.
        """
        self.__verify_can_access_environment(org, project, environment)
        logger.debug(
            f"Setting environment level context: {org}/{project}/{environment}"
        )
        self._context_level = ApiContextLevel.ENVIRONMENT
        self._organization = org
        self._project = project
        self._environment = environment
