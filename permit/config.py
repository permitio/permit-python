from typing import Optional

from .api.context import ApiContext
from .utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Field
else:
    from pydantic.v1 import BaseModel, Field  # type: ignore


class LoggerConfig(BaseModel):
    enable: bool = Field(default=False, description="Whether or not to enable logging from the Permit library")
    level: str = Field(default="info", description="Sets the log level configured for the Permit SDK Logger.")
    label: str = Field(
        default="Permit",
        description="Sets the label configured for logs emitted by the Permit SDK Logger.",
    )
    log_as_json: bool = Field(
        default=False,
        alias="json",
        description="Sets whether the SDK log output should be in JSON format.",
    )


class MultiTenancyConfig(BaseModel):
    default_tenant: str = Field(
        default="default",
        description="the key of the default tenant to be used if use_default_tenant_if_empty == True",
    )
    use_default_tenant_if_empty: bool = Field(
        default=True,
        description="whether or not the SDK should automatically associate a resource with the defaultTenant "
        + "if the resource provided in permit.check() was not associated with a tenant (i.e: undefined tenant).",
    )


class PermitConfig(BaseModel):
    token: str = Field(
        default=...,
        description="The token (API Key) used for authorization against the PDP and the Permit REST API.",
    )
    pdp: str = Field(
        default="http://localhost:7766",
        description="Configures the Policy Decision Point (PDP) url.",
    )
    api_url: str = Field(default="https://api.permit.io", description="The url of Permit REST API")
    log: LoggerConfig = Field(LoggerConfig(), description="the logger configuration used by the SDK")
    multi_tenancy: MultiTenancyConfig = Field(
        MultiTenancyConfig(),
        description="configuration of default tenant assignment for RBAC",
    )
    api_context: ApiContext = Field(ApiContext(), description="represents the current API key authorization level.")
    api_timeout: Optional[int] = Field(
        default=None,
        description="The timeout in seconds for requests to the Permit REST API.",
    )
    pdp_timeout: Optional[int] = Field(
        default=None,
        description="The timeout in seconds for requests to the PDP.",
    )
    proxy_facts_via_pdp: bool = Field(
        default=False,
        description="Create facts via the PDP API instead of using the default Permit REST API.",
    )
    facts_sync_timeout: Optional[float] = Field(
        default=None,
        description="The amount of time in seconds to wait for facts to be available "
        "in the PDP cache before returning the response.",
    )

    class Config:
        arbitrary_types_allowed = True
