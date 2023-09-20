from typing import List

from .api.context import ApiContext
from .utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Field
else:
    from pydantic.v1 import BaseModel, Field  # type: ignore


class LoggerConfig(BaseModel):
    enable: bool = Field(
        False, description="Whether or not to enable logging from the Permit library"
    )
    level: str = Field(
        "info", description="Sets the log level configured for the Permit SDK Logger."
    )
    label: str = Field(
        "Permit",
        description="Sets the label configured for logs emitted by the Permit SDK Logger.",
    )
    log_as_json: bool = Field(
        False,
        alias="json",
        description="Sets whether the SDK log output should be in JSON format.",
    )


class MultiTenancyConfig(BaseModel):
    default_tenant: str = Field(
        "default",
        description="the key of the default tenant to be used if use_default_tenant_if_empty == True",
    )
    use_default_tenant_if_empty: bool = Field(
        True,
        description="whether or not the SDK should automatically associate a resource with the defaultTenant "
        + "if the resource provided in permit.check() was not associated with a tenant (i.e: undefined tenant).",
    )


class PermitConfig(BaseModel):
    token: str = Field(
        ...,
        description="The token (API Key) used for authorization against the PDP and the Permit REST API.",
    )
    pdp: str = Field(
        "http://localhost:7766",
        description="Configures the Policy Decision Point (PDP) url.",
    )
    api_url: str = Field(
        "https://api.permit.io", description="The url of Permit REST API"
    )
    log: LoggerConfig = Field(
        LoggerConfig(), description="the logger configuration used by the SDK"
    )
    multi_tenancy: MultiTenancyConfig = Field(
        MultiTenancyConfig(),
        description="configuration of default tenant assignment for RBAC",
    )
    api_context: ApiContext = Field(
        ApiContext(), description="represents the current API key authorization level."
    )

    class Config:
        arbitrary_types_allowed = True
