from permit.utils.sync import SyncClass

from ..config import PermitConfig
from .role_assignments import RoleAssignmentsApi


class SyncRoleAssignmentsApi(RoleAssignmentsApi, metaclass=SyncClass):
    pass


class PermitPdpApiClient:
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


class SyncPDPApi(PermitPdpApiClient):
    def __init__(self, config: PermitConfig):
        self._role_assignments = SyncRoleAssignmentsApi(config)

    @property
    def role_assignments(self) -> SyncRoleAssignmentsApi:
        return self._role_assignments
