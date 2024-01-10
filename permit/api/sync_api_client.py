from ..config import PermitConfig
from ..utils.sync import SyncClass
from .condition_set_rules import ConditionSetRulesApi
from .condition_sets import ConditionSetsApi
from .deprecated import DeprecatedApi
from .environments import EnvironmentsApi
from .projects import ProjectsApi
from .relationship_tuples import RelationshipTuplesApi
from .resource_action_groups import ResourceActionGroupsApi
from .resource_actions import ResourceActionsApi
from .resource_attributes import ResourceAttributesApi
from .resource_instances import ResourceInstancesApi
from .resource_relations import ResourceRelationsApi
from .resource_roles import ResourceRolesApi
from .resources import ResourcesApi
from .role_assignments import RoleAssignmentsApi
from .roles import RolesApi
from .tenants import TenantsApi
from .users import UsersApi


class SyncConditionSetRulesApi(ConditionSetRulesApi, metaclass=SyncClass):
    pass


class SyncConditionSetsApi(ConditionSetsApi, metaclass=SyncClass):
    pass


class SyncDeprecatedApi(DeprecatedApi, metaclass=SyncClass):
    pass


class SyncEnvironmentsApi(EnvironmentsApi, metaclass=SyncClass):
    pass


class SyncProjectsApi(ProjectsApi, metaclass=SyncClass):
    pass


class SyncRelationshipTuplesApi(RelationshipTuplesApi, metaclass=SyncClass):
    pass


class SyncResourceActionGroupsApi(ResourceActionGroupsApi, metaclass=SyncClass):
    pass


class SyncResourceActionsApi(ResourceActionsApi, metaclass=SyncClass):
    pass


class SyncResourceAttributesApi(ResourceAttributesApi, metaclass=SyncClass):
    pass


class SyncResourceInstancesApi(ResourceInstancesApi, metaclass=SyncClass):
    pass


class SyncResourceRelationsApi(ResourceRelationsApi, metaclass=SyncClass):
    pass


class SyncResourceRolesApi(ResourceRolesApi, metaclass=SyncClass):
    pass


class SyncResourcesApi(ResourcesApi, metaclass=SyncClass):
    pass


class SyncRoleAssignmentsApi(RoleAssignmentsApi, metaclass=SyncClass):
    pass


class SyncRolesApi(RolesApi, metaclass=SyncClass):
    pass


class SyncTenantsApi(TenantsApi, metaclass=SyncClass):
    pass


class SyncUsersApi(UsersApi, metaclass=SyncClass):
    pass


class SyncPermitApiClient(SyncDeprecatedApi):
    def __init__(self, config: PermitConfig):
        """
        Constructs a new instance of the SyncPermitApiClient class with the specified SDK configuration.

        Args:
            config: The configuration for the Permit SDK.
        """
        super().__init__(config)

        self._condition_set_rules = SyncConditionSetRulesApi(config)
        self._condition_sets = SyncConditionSetsApi(config)
        self._environments = SyncEnvironmentsApi(config)
        self._projects = SyncProjectsApi(config)
        self._relationship_tuples = SyncRelationshipTuplesApi(config)
        self._action_groups = SyncResourceActionGroupsApi(config)
        self._resource_actions = SyncResourceActionsApi(config)
        self._resource_attributes = SyncResourceAttributesApi(config)
        self._resource_instances = SyncResourceInstancesApi(config)
        self._resource_relations = SyncResourceRelationsApi(config)
        self._resource_roles = SyncResourceRolesApi(config)
        self._resources = SyncResourcesApi(config)
        self._role_assignments = SyncRoleAssignmentsApi(config)
        self._roles = SyncRolesApi(config)
        self._tenants = SyncTenantsApi(config)
        self._users = SyncUsersApi(config)

    @property
    def condition_set_rules(self) -> SyncConditionSetRulesApi:
        """
        API for managing condition set rules.
        See: https://api.permit.io/v2/redoc#tag/Condition-Set-Rules
        """
        return self._condition_set_rules

    @property
    def condition_sets(self) -> SyncConditionSetsApi:
        """
        API for managing condition sets.
        See: https://api.permit.io/v2/redoc#tag/Condition-Sets
        """
        return self._condition_sets

    @property
    def projects(self) -> SyncProjectsApi:
        """
        API for managing projects.
        See: https://api.permit.io/v2/redoc#tag/Projects
        """
        return self._projects

    @property
    def environments(self) -> SyncEnvironmentsApi:
        """
        API for managing environments.
        See: https://api.permit.io/v2/redoc#tag/Environments
        """
        return self._environments

    @property
    def action_groups(self) -> SyncResourceActionGroupsApi:
        """
        API for managing resource action groups.
        See: https://api.permit.io/v2/redoc#tag/Resource-Action-Groups
        """
        return self._action_groups

    @property
    def resource_actions(self) -> SyncResourceActionsApi:
        """
        API for managing resource actions.
        See: https://api.permit.io/v2/redoc#tag/Resource-Actions
        """
        return self._resource_actions

    @property
    def resource_attributes(self) -> SyncResourceAttributesApi:
        """
        API for managing resource attributes.
        See: https://api.permit.io/v2/redoc#tag/Resource-Attributes
        """
        return self._resource_attributes

    @property
    def resource_roles(self) -> SyncResourceRolesApi:
        """
        API for managing resource roles.
        See: https://api.permit.io/v2/redoc#tag/Resource-Roles
        """
        return self._resource_roles

    @property
    def resource_relations(self) -> SyncResourceRelationsApi:
        """
        API for managing resource relations.
        See: https://api.permit.io/v2/redoc#tag/Resource-Relations
        """
        return self._resource_relations

    @property
    def resource_instances(self) -> SyncResourceInstancesApi:
        """
        API for managing resource instances.
        See: https://api.permit.io/v2/redoc#tag/Resource-Instances
        """
        return self._resource_instances

    @property
    def resources(self) -> SyncResourcesApi:
        """
        API for managing resources.
        See: https://api.permit.io/v2/redoc#tag/Resources
        """
        return self._resources

    @property
    def role_assignments(self) -> SyncRoleAssignmentsApi:
        """
        API for managing role assignments.
        See: https://api.permit.io/v2/redoc#tag/Role-Assignments
        """
        return self._role_assignments

    @property
    def relationship_tuples(self) -> SyncRelationshipTuplesApi:
        """
        API for managing relationship tuples.
        See: https://api.permit.io/v2/redoc#tag/Relationship-tuples
        """
        return self._relationship_tuples

    @property
    def roles(self) -> SyncRolesApi:
        """
        API for managing roles.
        See: https://api.permit.io/v2/redoc#tag/Roles
        """
        return self._roles

    @property
    def tenants(self) -> SyncTenantsApi:
        """
        API for managing tenants.
        See: https://api.permit.io/v2/redoc#tag/Tenants
        """
        return self._tenants

    @property
    def users(self) -> SyncUsersApi:
        """
        API for managing users.
        See: https://api.permit.io/v2/redoc#tag/Users
        """
        return self._users
