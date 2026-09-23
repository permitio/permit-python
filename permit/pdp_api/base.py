from typing import Any

from permit import PermitConfig
from permit.api.base import ClientConfig, SimpleHttpClient, pagination_params

__all__ = ["BasePdpPermitApi", "ClientConfig", "pagination_params"]


class BasePdpPermitApi:
    """The base class for Permit APIs."""

    def __init__(self, config: PermitConfig) -> None:
        """Initialize a BasePermitApi.

        Args:
            config: The Permit SDK configuration.
        """
        self.config = config

    def _build_http_client(self, endpoint_url: str = "", **kwargs: Any) -> SimpleHttpClient:
        client_config = ClientConfig(
            base_url=f"{self.config.pdp}",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"bearer {self.config.token}",
            },
        )
        client_config_dict = client_config.dict()
        client_config_dict.update(kwargs)
        return SimpleHttpClient(
            client_config_dict,
            base_url=endpoint_url,
            # pdp_timeout was documented on PermitConfig and honoured by the
            # enforcer, but silently ignored here, so every permit.pdp_api.*
            # call used aiohttp's default timeout instead of the configured one.
            timeout=self.config.pdp_timeout,
        )
