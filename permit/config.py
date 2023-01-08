from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from permit.constants import DEFAULT_PDP_URL
from permit.exceptions.exceptions import PermitContextException
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


class ApiKeyLevel(Enum):
    WAIT_FOR_INIT: None
    ORGANIZATION_LEVEL_API_KEY: 1
    PROJECT_LEVEL_API_KEY: 2
    ENVIRONMENT_LEVEL_API_KEY: 3


class LoggerConfig(BaseModel):
    level: str = Field("info", description="logging level")
    label: str = Field("Permit.io", description="label added to logs")
    log_as_json: bool = Field(
        False,
        alias="json",
        description="When logging - dump full data to console as JSON",
    )


class AutoMappingConfig(BaseModel):
    enable: bool = Field(
        False,
        description="Should the module automatically plugin to map frameworks on load",
    )
    ignored_url_prefixes: List[str] = Field(
        [],
        description="if auto mapping is on, ignore these prefixes when analyzing url paths",
    )
    review_mode: bool = Field(False, description="Print review and do nothing active")


class MultiTenancyConfig(BaseModel):
    default_tenant: str = Field(
        "default", description="the tenant key of the default tenant"
    )
    use_default_tenant_if_empty: bool = Field(
        True,
        description="if resource tenant was not specified, should we assume the default tenant?",
    )


class PermitContext(BaseModel):
    _api_key_level: ApiKeyLevel = Field(
        ApiKeyLevel.WAIT_FOR_INIT, description="The level of the client's API Key"
    )
    project: str = Field(
        None, description="The Project that the client will interact with"
    )
    environment: str = Field(
        None, description="The Environment that the client will interact with"
    )
    tenant: str = Field(
        None, description="The Tenant that the client will interact with"
    )


class ContextFactory:
    @staticmethod
    def build(project: str, environment: str, tenant: str,
              api_key_level: ApiKeyLevel) -> PermitContext:
        # if api_key_level == ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY and environment is None:
        #     raise PermitContextException()
        # if api_key_level == ApiKeyLevel.PROJECT_LEVEL_API_KEY and project is None:
        #     raise PermitContextException()
        return PermitContext(project=project, environment=environment, tenant=tenant)


class PermitConfig(BaseModel):
    api_url: str = Field(
        "https://api.permit.io", description="The url of Permit.io API"
    )
    token: str = Field(
        "", description="Your PDP token, used to authenticate to the PDP"
    )
    pdp: str = Field(DEFAULT_PDP_URL, description="Your PDP url")
    debug_mode: bool = Field(False, description="in debug mode we log more stuff")
    context: PermitContext = Field(None, description="Context that the client will use to interact with Permit.io")
    log: LoggerConfig = Field(LoggerConfig())
    auto_mapping: AutoMappingConfig = Field(AutoMappingConfig())
    multi_tenancy: MultiTenancyConfig = Field(MultiTenancyConfig())


class ConfigFactory:
    @staticmethod
    def build(options: dict) -> PermitConfig:
        config = PermitConfig(**options)
        # if no log level was set manually but debug mode is set,
        # we set the log level to debug/info respectively
        log_level_option = options.get("log", {}).get("level", None)
        if log_level_option is None:
            config.log.level = "debug" if config.debug_mode else "info"

        return config
