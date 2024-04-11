from typing import Callable, TypeVar

from permit import PYDANTIC_VERSION, PermitConfig
from permit.api.base import SimpleHttpClient

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Extra, Field, parse_obj_as
else:
    from pydantic.v1 import BaseModel, Extra, Field, parse_obj_as  # type: ignore


T = TypeVar("T", bound=Callable)
TModel = TypeVar("TModel", bound=BaseModel)
TData = TypeVar("TData", bound=BaseModel)


def pagination_params(page: int, per_page: int) -> dict:
    return {"page": page, "per_page": per_page}


class ClientConfig(BaseModel):
    class Config:
        extra = Extra.allow

    base_url: str = Field(
        ...,
        description="base url that will prefix the url fragment sent via the client",
    )
    headers: dict = Field(..., description="http headers sent to the API server")


class BasePdpPermitApi:
    """
    The base class for Permit APIs.
    """

    def __init__(self, config: PermitConfig):
        """
        Initialize a BasePermitApi.

        Args:
            config: The Permit SDK configuration.
        """
        self.config = config

    def _build_http_client(self, endpoint_url: str = "", **kwargs):
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
        )
