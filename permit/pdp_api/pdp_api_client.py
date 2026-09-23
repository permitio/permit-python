from permit.config import PermitConfig
from permit.pdp_api.role_assignments import RoleAssignmentsApi
from permit.utils.sync import SyncClass


class SyncRoleAssignmentsApi(RoleAssignmentsApi, metaclass=SyncClass):
    """Blocking variant of `RoleAssignmentsApi`."""


class PermitPdpApiClient:
    """Entry point to the APIs served by the PDP itself."""

    def __init__(self, config: PermitConfig) -> None:
        """Constructs a new instance of the PdpApiClient class with the specified SDK configuration.

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
        """Role assignments as the PDP currently sees them."""
        return self._role_assignments


class SyncPDPApi(PermitPdpApiClient):
    """Blocking variant of `PermitPdpApiClient`."""

    def __init__(self, config: PermitConfig) -> None:
        super().__init__(config)
        self._role_assignments = SyncRoleAssignmentsApi(config)

    @property
    def role_assignments(self) -> SyncRoleAssignmentsApi:
        """Role assignments as the PDP currently sees them."""
        return self._role_assignments  # type: ignore[return-value] # set to the sync type
