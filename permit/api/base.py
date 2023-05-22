import functools
from typing import Optional, Type, TypeVar, Union

import aiohttp
from loguru import logger
from pydantic import BaseModel, Extra, Field, parse_obj_as

from ..config import PermitConfig
from ..exceptions import PermitContextError, handle_api_error, handle_client_error
from .context import ApiKeyLevel
from .models import APIKeyScopeRead


class ClientConfig(BaseModel):
    class Config:
        extra = Extra.allow

    base_url: str = Field(
        ...,
        description="base url that will prefix the url fragment sent via the client",
    )
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


def pagination_params(page: int, per_page: int) -> dict:
    return {"page": page, "per_page": per_page}


TModel = TypeVar("TModel", bound=BaseModel)
TData = TypeVar("TData", bound=BaseModel)


class SimpleHttpClient:
    """
    wraps aiohttp client to reduce boilerplace
    """

    def __init__(self, client_config: dict, base_url: str = ""):
        self._client_config = client_config
        self._base_url = base_url

    def _log_request(self, url: str, method: str) -> None:
        logger.debug("Sending HTTP request: {} {}".format(method, url))

    def _log_response(self, url: str, method: str, status: int) -> None:
        logger.debug(
            "Received HTTP response: {} {}, status: {}".format(method, url, status)
        )

    def _prepare_json(
        self, json: Optional[Union[TData, dict, list]] = None
    ) -> Optional[dict]:
        if json is None:
            return None

        if isinstance(json, dict):
            return json

        if isinstance(json, list):
            return [self._prepare_json(item) for item in json]

        return json.dict(exclude_unset=True, exclude_none=True)

    @handle_client_error
    async def get(self, url, model: Type[TModel], **kwargs) -> TModel:
        url = f"{self._base_url}{url}"
        async with aiohttp.ClientSession(**self._client_config) as client:
            self._log_request(url, "GET")
            async with client.get(url, **kwargs) as response:
                await handle_api_error(response)
                self._log_response(url, "GET", response.status)
                data = await response.json()
                return parse_obj_as(model, data)

    @handle_client_error
    async def post(
        self,
        url,
        model: Type[TModel],
        json: Optional[Union[TData, dict, list]] = None,
        **kwargs,
    ) -> TModel:
        url = f"{self._base_url}{url}"
        async with aiohttp.ClientSession(**self._client_config) as client:
            self._log_request(url, "POST")
            async with client.post(
                url, json=self._prepare_json(json), **kwargs
            ) as response:
                await handle_api_error(response)
                self._log_response(url, "POST", response.status)
                data = await response.json()
                return parse_obj_as(model, data)

    @handle_client_error
    async def put(
        self,
        url,
        model: Type[TModel],
        json: Optional[Union[TData, dict, list]] = None,
        **kwargs,
    ) -> TModel:
        url = f"{self._base_url}{url}"
        async with aiohttp.ClientSession(**self._client_config) as client:
            self._log_request(url, "PUT")
            async with client.put(
                url, json=self._prepare_json(json), **kwargs
            ) as response:
                await handle_api_error(response)
                self._log_response(url, "PUT", response.status)
                data = await response.json()
                return parse_obj_as(model, data)

    @handle_client_error
    async def patch(
        self,
        url,
        model: Type[TModel],
        json: Optional[Union[TData, dict, list]] = None,
        **kwargs,
    ) -> TModel:
        url = f"{self._base_url}{url}"
        async with aiohttp.ClientSession(**self._client_config) as client:
            self._log_request(url, "PATCH")
            async with client.patch(
                url, json=self._prepare_json(json), **kwargs
            ) as response:
                await handle_api_error(response)
                self._log_response(url, "PATCH", response.status)
                data = await response.json()
                return parse_obj_as(model, data)

    @handle_client_error
    async def delete(
        self,
        url,
        model: Optional[Type[TModel]] = None,
        json: Optional[Union[TData, dict, list]] = None,
        **kwargs,
    ) -> Optional[TModel]:
        url = f"{self._base_url}{url}"
        async with aiohttp.ClientSession(**self._client_config) as client:
            self._log_request(url, "DELETE")
            async with client.delete(
                url, json=self._prepare_json(json), **kwargs
            ) as response:
                await handle_api_error(response)
                self._log_response(url, "DELETE", response.status)
                if model is None:
                    return None
                data = await response.json()
                return parse_obj_as(model, data)


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
        self.__api_keys = self._build_http_client("/v2/api-key")

    def _build_http_client(self, endpoint_url: str = "", **kwargs):
        client_config = ClientConfig(
            base_url=f"{self.config.api_url}",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"bearer {self.config.token}",
            },
        )
        client_config = client_config.dict()
        client_config.update(kwargs)
        return SimpleHttpClient(
            client_config,
            base_url=endpoint_url,
        )

    async def _set_context_from_api_key(self) -> None:
        """
        Set the API context based on the API key scope.
        """
        scope = await self.__api_keys.get("/scope", model=APIKeyScopeRead)

        if scope.organization_id is not None:
            if scope.project_id is not None:
                if scope.environment_id is not None:
                    # Set environment level context
                    self.config.api_context.set_environment_level_context(
                        scope.organization_id, scope.project_id, scope.environment_id
                    )
                    return

                # Set project level context
                self.config.api_context.set_project_level_context(
                    scope.organization_id, scope.project_id
                )
                return

            # Set org level context
            self.config.api_context.set_organization_level_context(
                scope.organization_id
            )
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
                f"You're trying to use an SDK method that requires an API Key with level: {call_level}, "
                + f"however the SDK is running with an API key with level {self.config.api_context.level}."
            )

        if (
            call_level == ApiKeyLevel.PROJECT_LEVEL_API_KEY
            and self.config.api_context.project is None
        ):
            raise PermitContextError(
                "You're trying to use an SDK method that's specific to a project, "
                + "but you haven't set the current project in your client's context yet, "
                + "or you are using an organization level API key. "
                + "Please set the context to a specific "
                + "project using `permit.set_context()` method."
            )

        if (
            call_level == ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY
            and self.config.api_context.environment is None
        ):
            raise PermitContextError(
                "You're trying to use an SDK method that's specific to an environment, "
                + "but you haven't set the current environment in your client's context yet, "
                + "or you are using an organization/project level API key. "
                + "Please set the context to a specific "
                + "environment using `permit.set_context()` method."
            )
