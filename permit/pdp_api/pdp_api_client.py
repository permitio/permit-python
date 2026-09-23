from typing import TYPE_CHECKING

from permit.utils.sync import SyncClass

from ..config import PermitConfig
from .role_assignments import RoleAssignmentsApi

# Type checkers read this class from a generated stub: the SyncClass metaclass
# makes its methods blocking at runtime, which they cannot see.
if TYPE_CHECKING:
    from permit._sync_types import SyncPdpRoleAssignmentsApi

    # An assignment, not `import ... as`: type checkers treat an import renamed
    # to a different name as private, and this name is part of the module's API.
    SyncRoleAssignmentsApi = SyncPdpRoleAssignmentsApi
else:

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
            "Authorization": f"Bearer {self._config.token}",
        }
        self._base_url = self._config.pdp

        self._role_assignments = RoleAssignmentsApi(config)

    @property
    def role_assignments(self) -> RoleAssignmentsApi:
        return self._role_assignments


# Holds the blocking role assignments client where the async base holds the async
# one, which breaks substitutability on purpose, hence the ignores.
class SyncPDPApi(PermitPdpApiClient):
    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self._role_assignments = SyncRoleAssignmentsApi(config)  # type: ignore[assignment]

    @property
    def role_assignments(self) -> SyncRoleAssignmentsApi:  # type: ignore[override]
        return self._role_assignments  # type: ignore[return-value]
