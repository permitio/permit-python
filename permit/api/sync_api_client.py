from typing import TYPE_CHECKING

from permit.api.condition_set_rules import ConditionSetRulesApi
from permit.api.condition_sets import ConditionSetsApi
from permit.api.deprecated import DeprecatedApi
from permit.api.environments import EnvironmentsApi
from permit.api.groups import GroupsApi
from permit.api.pdps import PdpsApi
from permit.api.projects import ProjectsApi
from permit.api.relationship_tuples import RelationshipTuplesApi
from permit.api.resource_action_groups import ResourceActionGroupsApi
from permit.api.resource_actions import ResourceActionsApi
from permit.api.resource_attributes import ResourceAttributesApi
from permit.api.resource_instances import ResourceInstancesApi
from permit.api.resource_relations import ResourceRelationsApi
from permit.api.resource_roles import ResourceRolesApi
from permit.api.resources import ResourcesApi
from permit.api.role_assignments import RoleAssignmentsApi
from permit.api.roles import RolesApi
from permit.api.tenants import TenantsApi
from permit.api.user_invites import UserInvitesApi
from permit.api.users import UsersApi
from permit.config import PermitConfig
from permit.utils.sync import SyncClass

# Type checkers read these classes from a generated stub: the SyncClass metaclass
# makes their methods blocking at runtime, which they cannot see.
if TYPE_CHECKING:
    from permit._sync_types import SyncConditionSetRulesApi as SyncConditionSetRulesApi
    from permit._sync_types import SyncConditionSetsApi as SyncConditionSetsApi
    from permit._sync_types import SyncDeprecatedApi as SyncDeprecatedApi
    from permit._sync_types import SyncEnvironmentsApi as SyncEnvironmentsApi
    from permit._sync_types import SyncGroupsApi as SyncGroupsApi
    from permit._sync_types import SyncPdpsApi as SyncPdpsApi
    from permit._sync_types import SyncProjectsApi as SyncProjectsApi
    from permit._sync_types import SyncRelationshipTuplesApi as SyncRelationshipTuplesApi
    from permit._sync_types import SyncResourceActionGroupsApi as SyncResourceActionGroupsApi
    from permit._sync_types import SyncResourceActionsApi as SyncResourceActionsApi
    from permit._sync_types import SyncResourceAttributesApi as SyncResourceAttributesApi
    from permit._sync_types import SyncResourceInstancesApi as SyncResourceInstancesApi
    from permit._sync_types import SyncResourceRelationsApi as SyncResourceRelationsApi
    from permit._sync_types import SyncResourceRolesApi as SyncResourceRolesApi
    from permit._sync_types import SyncResourcesApi as SyncResourcesApi
    from permit._sync_types import SyncRoleAssignmentsApi as SyncRoleAssignmentsApi
    from permit._sync_types import SyncRolesApi as SyncRolesApi
    from permit._sync_types import SyncTenantsApi as SyncTenantsApi
    from permit._sync_types import SyncUserInvitesApi as SyncUserInvitesApi
    from permit._sync_types import SyncUsersApi as SyncUsersApi
else:

    class SyncConditionSetRulesApi(ConditionSetRulesApi, metaclass=SyncClass):
        """Blocking variant of `ConditionSetRulesApi`."""

    class SyncConditionSetsApi(ConditionSetsApi, metaclass=SyncClass):
        """Blocking variant of `ConditionSetsApi`."""

    class SyncDeprecatedApi(DeprecatedApi, metaclass=SyncClass):
        """Blocking variant of `DeprecatedApi`."""

    class SyncEnvironmentsApi(EnvironmentsApi, metaclass=SyncClass):
        """Blocking variant of `EnvironmentsApi`."""

    class SyncGroupsApi(GroupsApi, metaclass=SyncClass):
        """Blocking variant of `GroupsApi`."""

    class SyncPdpsApi(PdpsApi, metaclass=SyncClass):
        """Blocking variant of `PdpsApi`."""

    class SyncProjectsApi(ProjectsApi, metaclass=SyncClass):
        """Blocking variant of `ProjectsApi`."""

    class SyncRelationshipTuplesApi(RelationshipTuplesApi, metaclass=SyncClass):
        """Blocking variant of `RelationshipTuplesApi`."""

    class SyncResourceActionGroupsApi(ResourceActionGroupsApi, metaclass=SyncClass):
        """Blocking variant of `ResourceActionGroupsApi`."""

    class SyncResourceActionsApi(ResourceActionsApi, metaclass=SyncClass):
        """Blocking variant of `ResourceActionsApi`."""

    class SyncResourceAttributesApi(ResourceAttributesApi, metaclass=SyncClass):
        """Blocking variant of `ResourceAttributesApi`."""

    class SyncResourceInstancesApi(ResourceInstancesApi, metaclass=SyncClass):
        """Blocking variant of `ResourceInstancesApi`."""

    class SyncResourceRelationsApi(ResourceRelationsApi, metaclass=SyncClass):
        """Blocking variant of `ResourceRelationsApi`."""

    class SyncResourceRolesApi(ResourceRolesApi, metaclass=SyncClass):
        """Blocking variant of `ResourceRolesApi`."""

    class SyncResourcesApi(ResourcesApi, metaclass=SyncClass):
        """Blocking variant of `ResourcesApi`."""

    class SyncRoleAssignmentsApi(RoleAssignmentsApi, metaclass=SyncClass):
        """Blocking variant of `RoleAssignmentsApi`."""

    class SyncRolesApi(RolesApi, metaclass=SyncClass):
        """Blocking variant of `RolesApi`."""

    class SyncTenantsApi(TenantsApi, metaclass=SyncClass):
        """Blocking variant of `TenantsApi`."""

    class SyncUserInvitesApi(UserInvitesApi, metaclass=SyncClass):
        """Blocking variant of `UserInvitesApi`."""

    class SyncUsersApi(UsersApi, metaclass=SyncClass):
        """Blocking variant of `UsersApi`."""


class SyncPermitApiClient(SyncDeprecatedApi):
    """Blocking variant of `PermitApiClient`."""

    def __init__(self, config: PermitConfig) -> None:
        """Constructs a new SyncPermitApiClient with the specified SDK configuration.

        Args:
            config: The configuration for the Permit SDK.
        """
        super().__init__(config)

        self._condition_set_rules = SyncConditionSetRulesApi(config)
        self._condition_sets = SyncConditionSetsApi(config)
        self._environments = SyncEnvironmentsApi(config)
        self._groups = SyncGroupsApi(config)
        self._pdps = SyncPdpsApi(config)
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
        self._user_invites = SyncUserInvitesApi(config)
        self._users = SyncUsersApi(config)

    @property
    def condition_set_rules(self) -> SyncConditionSetRulesApi:
        """API for managing condition set rules.

        See: https://api.permit.io/v2/redoc#tag/Condition-Set-Rules
        """
        return self._condition_set_rules

    @property
    def condition_sets(self) -> SyncConditionSetsApi:
        """API for managing condition sets.

        See: https://api.permit.io/v2/redoc#tag/Condition-Sets
        """
        return self._condition_sets

    @property
    def projects(self) -> SyncProjectsApi:
        """API for managing projects.

        See: https://api.permit.io/v2/redoc#tag/Projects
        """
        return self._projects

    @property
    def environments(self) -> SyncEnvironmentsApi:
        """API for managing environments.

        See: https://api.permit.io/v2/redoc#tag/Environments
        """
        return self._environments

    @property
    def groups(self) -> SyncGroupsApi:
        """API for managing groups.

        See: https://api.permit.io/v2/redoc#tag/Groups
        """
        return self._groups

    @property
    def pdps(self) -> SyncPdpsApi:
        """API for acting on the environment's PDPs, such as refreshing their data.

        See: https://api.permit.io/v2/redoc#tag/Policy-Decision-Points
        """
        return self._pdps

    @property
    def action_groups(self) -> SyncResourceActionGroupsApi:
        """API for managing resource action groups.

        See: https://api.permit.io/v2/redoc#tag/Resource-Action-Groups
        """
        return self._action_groups

    @property
    def resource_actions(self) -> SyncResourceActionsApi:
        """API for managing resource actions.

        See: https://api.permit.io/v2/redoc#tag/Resource-Actions
        """
        return self._resource_actions

    @property
    def resource_attributes(self) -> SyncResourceAttributesApi:
        """API for managing resource attributes.

        See: https://api.permit.io/v2/redoc#tag/Resource-Attributes
        """
        return self._resource_attributes

    @property
    def resource_roles(self) -> SyncResourceRolesApi:
        """API for managing resource roles.

        See: https://api.permit.io/v2/redoc#tag/Resource-Roles
        """
        return self._resource_roles

    @property
    def resource_relations(self) -> SyncResourceRelationsApi:
        """API for managing resource relations.

        See: https://api.permit.io/v2/redoc#tag/Resource-Relations
        """
        return self._resource_relations

    @property
    def resource_instances(self) -> SyncResourceInstancesApi:
        """API for managing resource instances.

        See: https://api.permit.io/v2/redoc#tag/Resource-Instances
        """
        return self._resource_instances

    @property
    def resources(self) -> SyncResourcesApi:
        """API for managing resources.

        See: https://api.permit.io/v2/redoc#tag/Resources
        """
        return self._resources

    @property
    def role_assignments(self) -> SyncRoleAssignmentsApi:
        """API for managing role assignments.

        See: https://api.permit.io/v2/redoc#tag/Role-Assignments
        """
        return self._role_assignments

    @property
    def relationship_tuples(self) -> SyncRelationshipTuplesApi:
        """API for managing relationship tuples.

        See: https://api.permit.io/v2/redoc#tag/Relationship-tuples
        """
        return self._relationship_tuples

    @property
    def roles(self) -> SyncRolesApi:
        """API for managing roles.

        See: https://api.permit.io/v2/redoc#tag/Roles
        """
        return self._roles

    @property
    def tenants(self) -> SyncTenantsApi:
        """API for managing tenants.

        See: https://api.permit.io/v2/redoc#tag/Tenants
        """
        return self._tenants

    @property
    def user_invites(self) -> SyncUserInvitesApi:
        """API for managing user invites.

        See: https://api.permit.io/v2/redoc#tag/User-Invites
        """
        return self._user_invites

    @property
    def users(self) -> SyncUsersApi:
        """API for managing users.

        See: https://api.permit.io/v2/redoc#tag/Users
        """
        return self._users
