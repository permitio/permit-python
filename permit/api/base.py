import functools
from typing import Callable, Optional, Type, TypeVar, Union

import aiohttp
from loguru import logger

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Extra, Field, parse_obj_as
else:
    from pydantic.v1 import BaseModel, Extra, Field, parse_obj_as  # type: ignore


from ..config import PermitConfig
from ..exceptions import PermitContextError, handle_api_error, handle_client_error
from .context import API_ACCESS_LEVELS, ApiContextLevel, ApiKeyAccessLevel
from .models import APIKeyScopeRead

T = TypeVar("T", bound=Callable)
TModel = TypeVar("TModel", bound=BaseModel)
TData = TypeVar("TData", bound=BaseModel)


def required_permissions(access_level: ApiKeyAccessLevel):
    def decorator(func: T) -> T:
        @functools.wraps(func)
        async def wrapped(self: BasePermitApi, *args, **kwargs):
            await self._ensure_access_level(access_level)
            return await func(self, *args, **kwargs)

        return wrapped

    return decorator


def required_context(context: ApiContextLevel):
    """
    a decorator that ensures that an API endpoint is called only after the SDK has initialized
    an API context (authorization level) by inferring it from the API key or manually by the user.

    Args:
        call_level: The required API key level for the endpoint.

    Raises:
        PermitContextError: If the API context does not match the required endpoint context.
    """

    def decorator(func: T) -> T:
        @functools.wraps(func)
        async def wrapped(self: BasePermitApi, *args, **kwargs):
            await self._ensure_context(context)
            return await func(self, *args, **kwargs)

        return wrapped

    return decorator


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
        Set the API context and permitted access level based on the API key scope.
        """
        logger.debug("Fetching api key scope")
        scope = await self.__api_keys.get("/scope", model=APIKeyScopeRead)

        if scope.organization_id is not None:
            # saves the permitted access level by that api key
            self.config.api_context._save_api_key_accessible_scope(
                org=str(scope.organization_id),
                project=(
                    str(scope.project_id) if scope.project_id is not None else None
                ),
                environment=(
                    str(scope.environment_id)
                    if scope.environment_id is not None
                    else None
                ),
            )

            if scope.project_id is not None:
                if scope.environment_id is not None:
                    # Set environment level context
                    self.config.api_context.set_environment_level_context(
                        str(scope.organization_id),
                        str(scope.project_id),
                        str(scope.environment_id),
                    )
                    return

                # Set project level context
                self.config.api_context.set_project_level_context(
                    str(scope.organization_id), str(scope.project_id)
                )
                return

            # Set org level context
            self.config.api_context.set_organization_level_context(
                str(scope.organization_id)
            )
            return

        raise PermitContextError("Could not set API context level")

    async def _ensure_access_level(
        self, required_access_level: ApiKeyAccessLevel
    ) -> None:
        """
        Ensure that the API Key has the necessary permissions to successfully call the API endpoint.

        Note that this check is not full proof, and the API may still throw 401.

        Args:
            required_access_level: The required API Key Access level for the endpoint.

        Raises:
            PermitContextError: If the currently set API key access level does not match the required access level.
        """
        # should only happen once in the lifetime of the sdk
        if (
            self.config.api_context.level == ApiContextLevel.WAIT_FOR_INIT
            or self.config.api_context.permitted_access_level
            == ApiKeyAccessLevel.WAIT_FOR_INIT
        ):
            await self._set_context_from_api_key()

        if required_access_level != self.config.api_context.permitted_access_level:
            if API_ACCESS_LEVELS.index(required_access_level) < API_ACCESS_LEVELS.index(
                self.config.api_context.permitted_access_level
            ):
                raise PermitContextError(
                    f"You're trying to use an SDK method that requires an API Key with access level: {required_access_level}, "
                    + f"however the SDK is running with an API key with level {self.config.api_context.permitted_access_level}."
                )
            return

        if (
            self.config.api_context.permitted_access_level.value
            < required_access_level.value
        ):
            raise PermitContextError(
                f"You're trying to use an SDK method that requires an api context of {required_context.name}, "
                + f"however the SDK is running in a less specific context level: {self.config.api_context.level}."
            )

    async def _ensure_context(self, required_context: ApiContextLevel) -> None:
        """
        Ensure that the API context matches the required endpoint context.

        Args:
            context: The required API context level for the endpoint.

        Raises:
            PermitContextError: If the currently set API context level does not match the required context level.
        """
        # should only happen once in the lifetime of the sdk
        if (
            self.config.api_context.level == ApiContextLevel.WAIT_FOR_INIT
            or self.config.api_context.permitted_access_level
            == ApiKeyAccessLevel.WAIT_FOR_INIT
        ):
            await self._set_context_from_api_key()

        if self.config.api_context.level.value < required_context.value:
            raise PermitContextError(
                f"You're trying to use an SDK method that requires an api context of {required_context.name}, "
                + f"however the SDK is running in a less specific context level: {self.config.api_context.level}."
            )
