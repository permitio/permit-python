from permit import PermitConfig
from permit.api.base import ClientConfig, SimpleHttpClient, pagination_params
from permit.utils.http_sessions import LoopSessions

__all__ = ["BasePdpPermitApi", "ClientConfig", "pagination_params"]


class BasePdpPermitApi:
    """The base class for Permit APIs."""

    def __init__(self, config: PermitConfig) -> None:
        """Initialize a BasePermitApi.

        Args:
            config: The Permit SDK configuration.
        """
        self.config = config
        self._sessions = LoopSessions()

    def _use_sessions(self, sessions: LoopSessions) -> None:
        """Send this API's requests through ``sessions`` from now on."""
        self._sessions = sessions

    def _build_http_client(self, endpoint_url: str = "") -> SimpleHttpClient:
        client_config = ClientConfig(
            base_url=f"{self.config.pdp}",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.token}",
            },
        )
        return SimpleHttpClient(
            client_config.dict(),
            base_url=endpoint_url,
            # pdp_timeout was documented on PermitConfig and honoured by the
            # enforcer, but silently ignored here, so every permit.pdp_api.*
            # call used aiohttp's default timeout instead of the configured one.
            timeout=self.config.pdp_timeout,
            sessions=self._sessions,
        )
