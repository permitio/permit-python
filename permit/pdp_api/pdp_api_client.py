from ..config import PermitConfig
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


class PermitApiClient(DeprecatedApi):
    def __init__(self, config: PermitConfig):
        """
        Constructs a new instance of the PdpApiClient class with the specified SDK configuration.

        Args:
            config: The configuration for the Permit SDK.
        """
        self._config = config
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {self._config.token}",
        }
        self._base_url = self._config.pdp

        self._role_assignments = RoleAssignmentsApi(config)

    @property
    def role_assignments(self) -> RoleAssignmentsApi:
        return self._role_assignments
