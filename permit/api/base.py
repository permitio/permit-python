from typing import TYPE_CHECKING, Any, TypeVar, cast, overload

from aiohttp import ClientResponse, ClientTimeout
from multidict import CIMultiDict
from yarl import URL

from permit.api.encoders import jsonable_encoder
from permit.utils.cloud_pdp import (
    USE_A_CONTAINER_PDP_FOR_FACTS,
    container_pdp_only_message,
    is_cloud_pdp_route_not_found,
)
from permit.utils.http_sessions import LoopSessions
from permit.utils.pydantic_version import PYDANTIC_VERSION
from permit.utils.sdk_logger import sdk_logger

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import BaseModel, Extra, Field, parse_obj_as
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, Extra, Field, parse_obj_as
else:
    from pydantic.v1 import BaseModel, Extra, Field, parse_obj_as

from permit.api.context import API_ACCESS_LEVELS, ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import APIKeyScopeRead
from permit.config import PermitConfig
from permit.exceptions import (
    PermitApiError,
    PermitContextError,
    handle_api_error,
    handle_client_error,
)

# Whatever `parse_obj_as` can build: a model, or e.g. `list[Model]` for list endpoints.
TModel = TypeVar("TModel")
# Unused by the SDK. Kept because it is importable from this module in 3.0.0.
TData = TypeVar("TData", bound=BaseModel)


def pagination_params(page: int, per_page: int) -> dict[str, str | int]:
    """Build the query parameters of a paginated list request.

    Args:
        page: The page number, starting at 1.
        per_page: How many items to fetch per page.

    Returns:
        The `page` and `per_page` query parameters.
    """
    return {"page": page, "per_page": per_page}


class ClientConfig(BaseModel):
    """Connection settings of a `SimpleHttpClient`."""

    class Config:
        extra = Extra.allow

    base_url: str = Field(
        ...,
        description="base url that will prefix the url fragment sent via the client",
    )
    # Bare `dict` on purpose: pydantic v1 passes it through as is, while a parameterized
    # dict would be validated as a mapping and copied.
    headers: dict = Field(  # type: ignore[type-arg]
        ..., description="http headers sent to the API server"
    )


# What a SimpleHttpClient's client_config may set. The other options of an aiohttp session
# cannot be set per client, since the client sends its requests through shared sessions.
_CLIENT_CONFIG_KEYS = frozenset({"base_url", "headers", "timeout"})


def _session_base_url(base_url: str | URL) -> URL:
    """``base_url`` as ``aiohttp.ClientSession(base_url=...)`` reads it, raising what it raises.

    Raises:
        ValueError: If ``base_url`` has no scheme or host, or its path does not end with "/".
    """
    if isinstance(base_url, URL):
        url = base_url
    else:
        url = URL(base_url)
        url.origin()  # raises ValueError for a URL without a scheme and a host
    if not url.path.endswith("/"):
        msg = "base_url must have a trailing '/'"
        raise ValueError(msg)
    return url


class SimpleHttpClient:
    """Sends requests to one endpoint and parses their JSON responses.

    The requests go through ``sessions``, which keep their connections open for the next
    request. Everything else a request carries comes from this client and the call itself,
    so the sessions can serve every client of an SDK client.

    Args:
        client_config: Optional request settings: ``base_url``, the server a relative request
            URL is resolved against, as ``aiohttp.ClientSession(base_url=...)`` resolves it;
            ``headers``, sent with every request; and ``timeout``, an
            ``aiohttp.ClientTimeout``.
        base_url: The endpoint's path, put before the URL of every request.
        timeout: The total timeout of each request in seconds, in place of
            ``client_config["timeout"]``.
        sessions: The sessions to send the requests through. Without them, the client has
            sessions of its own.
        container_pdp_advice: For a client of a PDP route that only the container PDP
            serves: what to do instead, said by the error it raises when the cloud PDP
            answers 404 for the route (see ``is_cloud_pdp_route_not_found``). The error is a
            ``PermitApiError`` that names the route and says it needs the container PDP.
            None, the default, for a route that every PDP, or the API, serves.

    Raises:
        TypeError: If ``client_config`` has a key other than those above.
    """

    def __init__(
        self,
        client_config: dict[str, Any],
        base_url: str = "",
        timeout: int | None = None,
        *,
        sessions: LoopSessions | None = None,
        container_pdp_advice: str | None = None,
    ) -> None:
        unsupported = sorted(set(client_config) - _CLIENT_CONFIG_KEYS)
        if unsupported:
            msg = (
                f"SimpleHttpClient does not take the client_config keys {unsupported}: "
                f"it sets only {sorted(_CLIENT_CONFIG_KEYS)} on its requests."
            )
            raise TypeError(msg)
        self._server_url: str | URL | None = client_config.get("base_url")
        self._headers: dict[str, str] | None = client_config.get("headers")
        self._timeout: ClientTimeout | None = (
            ClientTimeout(total=timeout) if timeout is not None else client_config.get("timeout")
        )
        self._base_url = base_url
        self._sessions = sessions if sessions is not None else LoopSessions()
        self._container_pdp_advice = container_pdp_advice

    def _use_sessions(self, sessions: LoopSessions) -> None:
        """Send the requests through ``sessions`` from now on."""
        self._sessions = sessions

    async def _raise_for_status(self, response: ClientResponse) -> None:
        """Raise the SDK's error for an error ``response``, as ``handle_api_error`` does.

        For a client of a route only the container PDP serves, the cloud PDP's 404 for the
        route is raised as a ``PermitApiError`` whose message names the route and says it
        needs the container PDP. The error's ``details`` hold the response's text, as for any
        body that is not JSON, and that message.
        """
        if self._container_pdp_advice is not None and await is_cloud_pdp_route_not_found(
            response, str(self._server_url)
        ):
            message = container_pdp_only_message(
                "The SDK",
                f"{response.method} {response.url.path}",
                str(self._server_url),
                self._container_pdp_advice,
            )
            text = await response.text(errors="replace")
            raise PermitApiError(response, {"details": text, "message": message}, message=message)
        await handle_api_error(response)

    def _request_url(self, url: str) -> URL:
        """``url`` resolved against the client's ``base_url``, as an aiohttp session does it.

        Raises:
            ValueError: If the client's ``base_url`` is not one an aiohttp session takes.
        """
        target = URL(url)
        if self._server_url is None:
            return target
        server_url = _session_base_url(self._server_url)
        return target if target.absolute else server_url.join(target)

    def _request_options(self, options: dict[str, Any]) -> dict[str, Any]:
        """The client's headers and timeout, with a request's own aiohttp ``options`` over them.

        The request's options win, as they did over the options of a session of the
        client's own: a header in ``options["headers"]`` replaces the client's header of
        that name.
        """
        headers = CIMultiDict(self._headers or {})
        headers.update(options.get("headers") or {})
        defaults = {} if self._timeout is None else {"timeout": self._timeout}
        return {**defaults, **options, "headers": headers}

    def _log_request(self, url: str, method: str) -> None:
        sdk_logger.debug(f"Sending HTTP request: {method} {url}")

    def _log_response(self, url: str, method: str, status: int) -> None:
        sdk_logger.debug(f"Received HTTP response: {method} {url}, status: {status}")

    def _prepare_json(
        self, json: BaseModel | dict[str, Any] | list[Any] | None = None
    ) -> dict[str, Any] | list[Any] | None:
        """Normalize a request body into JSON-serializable primitives.

        Models, dicts and lists all go through the same encoder so that nested
        ``datetime``/``UUID``/``Enum``/``Decimal`` values are encoded wherever they appear.

        Only ``exclude_unset`` is applied: a model field that was never set is omitted,
        while a field explicitly set to ``None`` is transmitted as JSON ``null`` so the
        API can distinguish "leave this alone" from "clear this value".

        Args:
            json: The request body, as a pydantic model, a dict, a list or ``None``.

        Returns:
            The encoded body, or ``None`` when no body was given.
        """
        if json is None:
            return None

        return cast("dict[str, Any] | list[Any]", jsonable_encoder(json, exclude_unset=True))

    @handle_client_error
    async def get(self, url: str, model: type[TModel], **kwargs: Any) -> TModel:
        """Send a GET request and parse the JSON response into `model`."""
        url = f"{self._base_url}{url}"
        target = self._request_url(url)
        client = await self._sessions.current()
        self._log_request(url, "GET")
        async with client.get(target, **self._request_options(kwargs)) as response:
            await self._raise_for_status(response)
            self._log_response(url, "GET", response.status)
            data = await response.json()
            return parse_obj_as(model, data)

    @handle_client_error
    async def post(
        self,
        url: str,
        model: type[TModel],
        json: BaseModel | dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> TModel:
        """Send a POST request with a JSON body and parse the JSON response into `model`."""
        url = f"{self._base_url}{url}"
        target = self._request_url(url)
        client = await self._sessions.current()
        self._log_request(url, "POST")
        async with client.post(
            target, json=self._prepare_json(json), **self._request_options(kwargs)
        ) as response:
            await self._raise_for_status(response)
            self._log_response(url, "POST", response.status)
            data = await response.json()
            return parse_obj_as(model, data)

    @handle_client_error
    async def put(
        self,
        url: str,
        model: type[TModel],
        json: BaseModel | dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> TModel:
        """Send a PUT request with a JSON body and parse the JSON response into `model`."""
        url = f"{self._base_url}{url}"
        target = self._request_url(url)
        client = await self._sessions.current()
        self._log_request(url, "PUT")
        async with client.put(
            target, json=self._prepare_json(json), **self._request_options(kwargs)
        ) as response:
            await self._raise_for_status(response)
            self._log_response(url, "PUT", response.status)
            data = await response.json()
            return parse_obj_as(model, data)

    @handle_client_error
    async def patch(
        self,
        url: str,
        model: type[TModel],
        json: BaseModel | dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> TModel:
        """Send a PATCH request with a JSON body and parse the JSON response into `model`."""
        url = f"{self._base_url}{url}"
        target = self._request_url(url)
        client = await self._sessions.current()
        self._log_request(url, "PATCH")
        async with client.patch(
            target, json=self._prepare_json(json), **self._request_options(kwargs)
        ) as response:
            await self._raise_for_status(response)
            self._log_response(url, "PATCH", response.status)
            data = await response.json()
            return parse_obj_as(model, data)

    @overload
    async def delete(
        self,
        url: str,
        model: None = None,
        json: BaseModel | dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> None: ...

    @overload
    async def delete(
        self,
        url: str,
        model: type[TModel],
        json: BaseModel | dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> TModel: ...

    @handle_client_error
    async def delete(
        self,
        url: str,
        model: type[TModel] | None = None,
        json: BaseModel | dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> TModel | None:
        """Send a DELETE request; parse the JSON response into `model` if one is given."""
        url = f"{self._base_url}{url}"
        target = self._request_url(url)
        client = await self._sessions.current()
        self._log_request(url, "DELETE")
        async with client.delete(
            target, json=self._prepare_json(json), **self._request_options(kwargs)
        ) as response:
            await self._raise_for_status(response)
            self._log_response(url, "DELETE", response.status)
            if model is None:
                return None
            data = await response.json()
            return parse_obj_as(model, data)


class BasePermitApi:
    """The base class for Permit APIs."""

    def __init__(self, config: PermitConfig) -> None:
        """Initialize a BasePermitApi.

        Args:
            config: The Permit SDK configuration.
        """
        self.config = config
        self._sessions = LoopSessions()
        self.__api_keys = self._build_http_client("/v2/api-key")

    def _use_sessions(self, sessions: LoopSessions) -> None:
        """Send the requests of this API and of the APIs and clients it holds through ``sessions``.

        A Permit client calls it so that all of its APIs share one session per event loop.
        """
        self._sessions = sessions
        for value in vars(self).values():
            if isinstance(value, (BasePermitApi, SimpleHttpClient)):
                value._use_sessions(sessions)  # noqa: SLF001 - SDK-internal

    def _build_http_client(
        self, endpoint_url: str = "", *, use_pdp: bool = False
    ) -> SimpleHttpClient:
        optional_headers = {}
        if self.config.proxy_facts_via_pdp:
            if self.config.facts_sync_timeout:
                optional_headers["X-Wait-Timeout"] = str(self.config.facts_sync_timeout)
            if self.config.facts_sync_timeout_policy:
                optional_headers["X-Timeout-Policy"] = str(self.config.facts_sync_timeout_policy)

        client_config = ClientConfig(
            base_url=self.config.pdp if use_pdp else self.config.api_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.token}",
                **optional_headers,
            },
        )
        return SimpleHttpClient(
            client_config.dict(),
            base_url=endpoint_url,
            timeout=self.config.api_timeout,
            sessions=self._sessions,
            container_pdp_advice=USE_A_CONTAINER_PDP_FOR_FACTS if use_pdp else None,
        )

    async def _set_context_from_api_key(self) -> None:
        """Set the API context and permitted access level based on the API key scope."""
        sdk_logger.debug("Fetching api key scope")
        scope = await self.__api_keys.get("/scope", model=APIKeyScopeRead)

        if scope.organization_id is not None:
            # saves the permitted access level by that api key
            self.config.api_context._save_api_key_accessible_scope(  # noqa: SLF001 - SDK-internal
                org=str(scope.organization_id),
                project=(str(scope.project_id) if scope.project_id is not None else None),
                environment=(
                    str(scope.environment_id) if scope.environment_id is not None else None
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
            self.config.api_context.set_organization_level_context(str(scope.organization_id))
            return

        # Defensive: the schema makes organization_id required, so mypy knows this
        # is unreachable for a well-formed response.
        msg = "Could not set API context level"  # type: ignore[unreachable]
        raise PermitContextError(msg)

    async def _ensure_access_level(self, required_access_level: ApiKeyAccessLevel) -> None:
        """Ensure that the API Key has the access level the API endpoint requires.

        Note that this check is not full proof, and the API may still throw 401.

        Args:
            required_access_level: The required API Key Access level for the endpoint.

        Raises:
            PermitContextError: If the currently set API key access level does not match the
                required access level.
        """
        # should only happen once in the lifetime of the sdk
        if (
            self.config.api_context.level == ApiContextLevel.WAIT_FOR_INIT
            or self.config.api_context.permitted_access_level == ApiKeyAccessLevel.WAIT_FOR_INIT
        ):
            await self._set_context_from_api_key()

        permitted_access_level = self.config.api_context.permitted_access_level
        if required_access_level != permitted_access_level and API_ACCESS_LEVELS.index(
            required_access_level
        ) < API_ACCESS_LEVELS.index(permitted_access_level):
            msg = (
                f"You're trying to use an SDK method that requires an API Key "
                f"with access level: {required_access_level}, however the SDK is running "
                f"with an API key with level {permitted_access_level}."
            )
            raise PermitContextError(msg)

    async def _ensure_context(self, required_context: ApiContextLevel) -> None:
        """Ensure that the API context matches the required endpoint context.

        Args:
            required_context: The required API context level for the endpoint.

        Raises:
            PermitContextError: If the currently set API context level does not match the required
                context level.
        """
        # should only happen once in the lifetime of the sdk
        if (
            self.config.api_context.level == ApiContextLevel.WAIT_FOR_INIT
            or self.config.api_context.permitted_access_level == ApiKeyAccessLevel.WAIT_FOR_INIT
        ):
            await self._set_context_from_api_key()

        if self.config.api_context.level.value < required_context.value:
            msg = (
                f"You're trying to use an SDK method that requires an api context of "
                f"{required_context.name}, "
                f"however the SDK is running in a less specific context level: "
                f"{self.config.api_context.level}."
            )
            raise PermitContextError(msg)
