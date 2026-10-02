from typing import TYPE_CHECKING

from permit.config import PermitConfig
from permit.pdp_api.role_assignments import RoleAssignmentsApi
from permit.utils.http_sessions import LoopSessions
from permit.utils.sync import SyncClass

# Type checkers read this class from a generated stub: the SyncClass metaclass
# makes its methods blocking at runtime, which they cannot see.
if TYPE_CHECKING:
    from permit._sync_types import SyncPdpRoleAssignmentsApi

    # An assignment, not `import ... as`: type checkers treat an import renamed
    # to a different name as private, and this name is part of the module's API.
    SyncRoleAssignmentsApi = SyncPdpRoleAssignmentsApi
else:

    class SyncRoleAssignmentsApi(RoleAssignmentsApi, metaclass=SyncClass):
        """Blocking variant of `RoleAssignmentsApi`."""


class PermitPdpApiClient:
    """Entry point to the APIs served by the PDP itself, which only the container PDP serves."""

    def __init__(self, config: PermitConfig) -> None:
        """Constructs a new instance of the PdpApiClient class with the specified SDK configuration.

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

    def _use_sessions(self, sessions: LoopSessions) -> None:
        """Send the requests of every API of this client through ``sessions`` from now on."""
        self._role_assignments._use_sessions(sessions)  # noqa: SLF001 - SDK-internal

    @property
    def role_assignments(self) -> RoleAssignmentsApi:
        """Role assignments as the PDP currently sees them."""
        return self._role_assignments


# Holds the blocking role assignments client where the async base holds the async
# one, which breaks substitutability on purpose, hence the ignores.
class SyncPDPApi(PermitPdpApiClient):
    """Blocking variant of `PermitPdpApiClient`."""

    def __init__(self, config: PermitConfig) -> None:
        super().__init__(config)
        self._role_assignments = SyncRoleAssignmentsApi(config)  # type: ignore[assignment]

    @property
    def role_assignments(self) -> SyncRoleAssignmentsApi:  # type: ignore[override]
        """Role assignments as the PDP currently sees them."""
        return self._role_assignments  # type: ignore[return-value]
