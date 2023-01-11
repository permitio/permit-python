from __future__ import annotations

from enum import Enum
from logging import Logger
from typing import List

from pydantic import BaseModel, Field

from permit.openapi.models import HTTPValidationError
from permit.constants import DEFAULT_PDP_URL, DEFAULT_TENANT_KEY
from permit.exceptions.exceptions import PermitContextError
from permit.openapi import AuthenticatedClient
from permit.openapi.api.api_keys import get_api_key_scope
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


class ApiKeyLevel(Enum):
    WAIT_FOR_INIT = 0
    ORGANIZATION_LEVEL_API_KEY = 1
    PROJECT_LEVEL_API_KEY = 2
    ENVIRONMENT_LEVEL_API_KEY = 3


class LoggerConfig(BaseModel):
    level: str = Field("details", description="logging level")
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
    api_key_level: ApiKeyLevel = Field(
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
    async def build(
        client: AuthenticatedClient, project: str = None, environment: str = None, tenant: str = DEFAULT_TENANT_KEY,
        is_user_input: bool = False
    ) -> PermitContext:
        res = await get_api_key_scope.asyncio(client=client)
        if res is None or isinstance(res, HTTPValidationError):
            raise PermitContextError(message="could not get api key scope in order to create a context")
        api_key_level = get_api_key_level(res)
        if not is_user_input:
            return PermitContext(project=res.project_id.hex,
                                 environment=res.environment_id.hex,
                                 tenant=tenant,
                                 api_key_level=api_key_level)
        if api_key_level == ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY:
            if environment is None or project is None:
                raise PermitContextError(
                    message="You initiated the Permit.io Client with an Environment level API key,"
                            " please set a context with the API key related environment and project")
        if api_key_level == ApiKeyLevel.PROJECT_LEVEL_API_KEY:
            if project is None:
                raise PermitContextError(
                    message="You initiated the Permit.io Client with a Project level API key,"
                            " please set a context with the API key related project")

        return PermitContext(project=project, environment=environment, tenant=tenant, api_key_level=api_key_level)


class PermitConfig(BaseModel):
    api_url: str = Field(
        "https://api.permit.io", description="The url of Permit.io API"
    )
    token: str = Field(
        "", description="Your PDP token, used to authenticate to the PDP"
    )
    pdp: str = Field(DEFAULT_PDP_URL, description="Your PDP url")
    debug_mode: bool = Field(False, description="in debug mode we log more stuff")
    context: PermitContext = Field(
        None, description="Context that the client will use to interact with Permit.io"
    )
    log: LoggerConfig = Field(LoggerConfig())
    auto_mapping: AutoMappingConfig = Field(AutoMappingConfig())
    multi_tenancy: MultiTenancyConfig = Field(MultiTenancyConfig())


class ConfigFactory:
    @staticmethod
    def build(options: dict) -> PermitConfig:
        config = PermitConfig(**options)
        # if no log level was set manually but debug mode is set,
        # we set the log level to debug/details respectively
        log_level_option = options.get("log", {}).get("level", None)
        if log_level_option is None:
            config.log.level = "debug" if config.debug_mode else "details"

        return config


def get_api_key_level(scope: APIKeyScopeRead) -> ApiKeyLevel:
    if scope.environment_id is not None:
        return ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY
    if scope.project_id is not None:
        return ApiKeyLevel.PROJECT_LEVEL_API_KEY
    return ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY
