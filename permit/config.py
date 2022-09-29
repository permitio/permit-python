from typing import List

from pydantic import BaseModel, Field

from permit.constants import DEFAULT_PDP_URL


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


class PermitConfig(BaseModel):
    api_url: str = Field(
        "https://api.permit.io", description="The url of Permit.io API"
    )
    token: str = Field(
        "", description="Your PDP token, used to authenticate to the PDP"
    )
    pdp: str = Field(DEFAULT_PDP_URL, description="Your PDP url")
    debug_mode: bool = Field(False, description="in debug mode we log more stuff")
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
