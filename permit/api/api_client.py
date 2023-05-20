from typing import Optional

from permit.api.condition_set_rules import ConditionSetRulesApi
from permit.api.condition_sets import ConditionSetsApi
from permit.api.deprecated import DeprecatedApi
from permit.api.environments import EnvironmentsApi
from permit.api.projects import ProjectsApi
from permit.api.resource_action_groups import ResourceActionGroupsApi
from permit.api.resource_actions import ResourceActionsApi
from permit.api.resource_attributes import ResourceAttributesApi
from permit.api.resources import ResourcesApi
from permit.api.role_assignments import RoleAssignmentsApi
from permit.api.roles import RolesApi
from permit.api.tenants import TenantsApi
from permit.api.users import UsersApi
from permit.config import PermitConfig


class ApiClient(DeprecatedApi):
    def __init__(self, config: PermitConfig):
        """
        Constructs a new instance of the ApiClient class with the specified SDK configuration.

        Args:
            config: The configuration for the Permit SDK.
        """
        super().__init__(config)

        self._condition_set_rules = ConditionSetRulesApi(config)
        self._condition_sets = ConditionSetsApi(config)
        self._environments = EnvironmentsApi(config)
        self._projects = ProjectsApi(config)
        self._action_groups = ResourceActionGroupsApi(config)
        self._resource_actions = ResourceActionsApi(config)
        self._resource_attributes = ResourceAttributesApi(config)
        self._resources = ResourcesApi(config)
        self._role_assignments = RoleAssignmentsApi(config)
        self._roles = RolesApi(config)
        self._tenants = TenantsApi(config)
        self._users = UsersApi(config)

    @property
    def condition_set_rules(self) -> ConditionSetRulesApi:
        """
        API for managing condition set rules.
        See: https://api.permit.io/v2/redoc#tag/Condition-Set-Rules
        """
        return self._condition_set_rules

    @property
    def condition_sets(self) -> ConditionSetsApi:
        """
        API for managing condition sets.
        See: https://api.permit.io/v2/redoc#tag/Condition-Sets
        """
        return self._condition_sets

    @property
    def projects(self) -> ProjectsApi:
        """
        API for managing projects.
        See: https://api.permit.io/v2/redoc#tag/Projects
        """
        return self._projects

    @property
    def environments(self) -> EnvironmentsApi:
        """
        API for managing environments.
        See: https://api.permit.io/v2/redoc#tag/Environments
        """
        return self._environments

    @property
    def action_groups(self) -> ResourceActionGroupsApi:
        """
        API for managing resource action groups.
        See: https://api.permit.io/v2/redoc#tag/Resource-Action-Groups
        """
        return self._action_groups

    @property
    def resource_actions(self) -> ResourceActionsApi:
        """
        API for managing resource actions.
        See: https://api.permit.io/v2/redoc#tag/Resource-Actions
        """
        return self._resource_actions

    @property
    def resource_attributes(self) -> ResourceAttributesApi:
        """
        API for managing resource attributes.
        See: https://api.permit.io/v2/redoc#tag/Resource-Attributes
        """
        return self._resource_attributes

    @property
    def resources(self) -> ResourcesApi:
        """
        API for managing resources.
        See: https://api.permit.io/v2/redoc#tag/Resources
        """
        return self._resources

    @property
    def role_assignments(self) -> RoleAssignmentsApi:
        """
        API for managing role assignments.
        See: https://api.permit.io/v2/redoc#tag/Role-Assignments
        """
        return self._role_assignments

    @property
    def roles(self) -> RolesApi:
        """
        API for managing roles.
        See: https://api.permit.io/v2/redoc#tag/Roles
        """
        return self._roles

    @property
    def tenants(self) -> TenantsApi:
        """
        API for managing tenants.
        See: https://api.permit.io/v2/redoc#tag/Tenants
        """
        return self._tenants

    @property
    def users(self) -> UsersApi:
        """
        API for managing users.
        See: https://api.permit.io/v2/redoc#tag/Users
        """
        return self._users