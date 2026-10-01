from typing import TYPE_CHECKING, Literal

from permit.api.context import ApiContext
from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import BaseModel, Field
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Field
else:
    from pydantic.v1 import BaseModel, Field


class LoggerConfig(BaseModel):
    """Logging settings of the SDK.

    The SDK logs with loguru and adds no sink of its own: its records go to the loguru sinks
    the application has added, or to loguru's default stderr sink, in the format of those
    sinks. loguru's logger is process-wide, so these settings are too: the client created
    last decides whether the SDK logs, and the last one created with `enable` True decides
    the level and the label, for every client in the process.

    Whatever these settings, the SDK replaces the API key of every client in the process
    with `[REDACTED]` in the messages it logs and in the PDP error bodies it puts in a
    `PermitConnectionError`. A user name and password written into the `api_url` or `pdp`
    URL are not replaced.
    """

    enable: bool = Field(
        default=False,
        description="Whether the SDK logs. False calls loguru's logger.disable('permit'), so "
        "nothing is logged. True undoes that call with logger.enable('permit') if an earlier "
        "client made it, and otherwise leaves loguru's switches alone, so a logger.disable() "
        "the application made for 'permit' or one of its modules still applies.",
    )
    level: str = Field(
        default="info",
        description="The lowest severity the SDK logs, such as 'debug', 'info', 'warning' or "
        "'error', in any case; 'warn' and 'fatal' are read as 'warning' and 'critical'. The SDK "
        "drops its records below it before they reach any sink. "
        "Read only when enable is True; a name loguru does not know raises ValueError when the "
        "client is created.",
    )
    label: str = Field(
        default="Permit",
        description="Put in square brackets before the message of every record the SDK logs, "
        "as in '[Permit] ...'. An empty string adds nothing. Read only when enable is True.",
    )
    log_as_json: bool = Field(
        default=False,
        alias="json",
        description="Not applied. The format of the SDK's records is that of the loguru sinks "
        "they reach: for JSON, add a sink with logger.add(..., serialize=True).",
    )


class MultiTenancyConfig(BaseModel):
    """How resources without a tenant are assigned one."""

    default_tenant: str = Field(
        default="default",
        description="the key of the default tenant to be used "
        "if use_default_tenant_if_empty == True",
    )
    use_default_tenant_if_empty: bool = Field(
        default=True,
        description="whether or not the SDK should automatically associate a resource "
        "with the defaultTenant "
        "if the resource provided in permit.check() was not associated with a tenant "
        "(i.e: undefined tenant).",
    )


class PermitConfig(BaseModel):
    """Configuration of the Permit SDK."""

    # A positional `...`, not `default=...`: type checkers take any `default=`
    # keyword as a default, so `PermitConfig()` without a token would pass them.
    # repr=False keeps the key out of repr() and str() of the config, and so out of
    # tracebacks that print frame values, such as loguru's with diagnose=True.
    token: str = Field(
        ...,
        repr=False,
        description="The token (API Key) used for authorization against the PDP "
        "and the Permit REST API.",
    )
    pdp: str = Field(
        default="http://localhost:7766",
        description="Configures the Policy Decision Point (PDP) url.",
    )
    api_url: str = Field(default="https://api.permit.io", description="The url of Permit REST API")
    log: LoggerConfig = Field(
        default=LoggerConfig(), description="the logger configuration used by the SDK"
    )
    multi_tenancy: MultiTenancyConfig = Field(
        default=MultiTenancyConfig(),
        description="configuration of default tenant assignment for RBAC",
    )
    api_context: ApiContext = Field(
        default=ApiContext(), description="represents the current API key authorization level."
    )
    api_timeout: int | None = Field(
        default=None,
        description="The timeout in seconds for requests to the Permit REST API.",
    )
    pdp_timeout: int | None = Field(
        default=None,
        description="The timeout in seconds for requests to the PDP.",
    )
    proxy_facts_via_pdp: bool = Field(
        default=False,
        description="Create facts via the PDP API instead of using the default Permit REST API.",
    )
    facts_sync_timeout: float | None = Field(
        default=None,
        description="The amount of time in seconds to wait for facts to be available "
        "in the PDP cache before returning the response.",
    )
    facts_sync_timeout_policy: Literal["ignore", "fail"] | None = Field(
        default=None,
        description="The policy to apply when the facts sync timeout is reached.",
    )

    class Config:
        arbitrary_types_allowed = True
