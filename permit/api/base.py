import functools
import aiohttp

from typing import TypeVar, Optional
from loguru import logger

from pydantic import BaseModel, Field, Extra

from permit.api.context import ApiKeyLevel
from permit.api.models import APIKeyScopeRead
from permit.config import PermitConfig
from permit.exceptions import handle_api_error, handle_client_error, PermitContextError


class ClientConfig(BaseModel):
    class Config:
        extra = Extra.allow

    base_url: str = Field(..., description="base url that will prefix the url fragment sent via the client")
    headers: dict = Field(..., description="http headers sent to the API server")


def ensure_context(call_level: ApiKeyLevel):
    """
    a decorator that ensures that an API endpoint is called only after the SDK has initialized
    an API context (authorization level) by inferring it from the API key or manually by the user.

    Args:
        call_level: The required API key level for the endpoint.

    Raises:
        PermitContextError: If the API context does not match the required endpoint context.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapped(self: BasePermitApi, *args, **kwargs):
            await self.ensure_context(call_level)
            return await func(self, *args, **kwargs)
        return wrapped
    return decorator


class BasePermitApi:
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
        self._api_keys = self._build_http_client('/v2/api-key')
    
    def _build_http_client(self, endpoint_url: str, **kwargs):
        client_config = ClientConfig(
            base_url = f"{self.config.api_url}{endpoint_url}",
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"bearer {self.config.token}",
            }
        )
        return aiohttp.ClientSession(**client_config.dict(), **kwargs)
    
    @handle_client_error
    async def _get_api_key_scope(self) -> APIKeyScopeRead:
        async with self._api_keys as client:
            async with client.get("/scope") as response:
                handle_api_error(response)
                data = await response.json()
                return APIKeyScopeRead(**data)

    async def _set_context_from_api_key(self) -> None:
        """
        Set the API context based on the API key scope.
        """
        scope = await self._get_api_key_scope()

        if scope.organization_id is not None:
            if scope.project_id is not None:
                if scope.environment_id is not None:
                    # Set environment level context
                    self.config.api_context.set_environment_level_context(
                        scope.organization_id,
                        scope.project_id,
                        scope.environment_id
                    )
                    return

                # Set project level context
                self.config.api_context.set_project_level_context(
                    scope.organization_id,
                    scope.project_id
                )
                return

            # Set org level context
            self.config.api_context.set_organization_level_context(scope.organization_id)
            return

        raise PermitContextError("Could not set API context level")

    async def ensure_context(self, call_level: ApiKeyLevel) -> None:
        """
        Ensure that the API context matches the required endpoint context.

        Args:
            call_level: The required API key level for the endpoint.

        Raises:
            PermitContextError: If the API context does not match the required endpoint context.
        """
        if self.config.api_context.level == ApiKeyLevel.WAIT_FOR_INIT:
            await self._set_context_from_api_key()

        if call_level != self.config.api_context.level:
            raise PermitContextError(
                f"You're trying to use an SDK method that requires an API Key with level: {call_level}, " +
                f"however the SDK is running with an API key with level {self.config.api_context.level}."
            )

        if (
            call_level == ApiKeyLevel.PROJECT_LEVEL_API_KEY
            and self.config.api_context.project is None
        ):
            raise PermitContextError(
                "You're trying to use an SDK method that's specific to a project, " +
                "but you haven't set the current project in your client's context yet, " +
                "or you are using an organization level API key. " +
                "Please set the context to a specific " +
                "project using `permit.set_context()` method."
            )

        if (
            call_level == ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY
            and self.config.api_context.environment is None
        ):
            raise PermitContextError(
                "You're trying to use an SDK method that's specific to an environment, " +
                "but you haven't set the current environment in your client's context yet, " +
                "or you are using an organization/project level API key. " +
                "Please set the context to a specific " +
                "environment using `permit.set_context()` method."
            )
