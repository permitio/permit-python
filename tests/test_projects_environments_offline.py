"""Offline wire tests for permit.api.projects and permit.api.environments (PER-16177).

Every public method is called through the async and the blocking client, each closed once
the call returns, with an API key of the narrowest level the method accepts. The test checks
the request it puts on the wire (method, path, query string, headers and JSON body), what
the response parses into, that the API's error response raises the matching
``PermitApiError``, and that a key one level narrower is refused before anything is sent.
Every request is served by a local ``pytest_httpserver`` and the API context is
pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
import re
from operator import attrgetter
from typing import Any, NamedTuple

import pytest
from pydantic.v1 import BaseModel
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.api.context import API_ACCESS_LEVELS, ApiKeyAccessLevel
from permit.api.environments import EnvironmentsApi
from permit.api.models import (
    APIKeyRead,
    EnvironmentRead,
    EnvironmentStats,
    ProjectCreate,
    ProjectRead,
)
from permit.api.projects import ProjectsApi
from permit.config import PermitConfig
from permit.exceptions import (
    PermitAlreadyExistsError,
    PermitApiDetailedError,
    PermitApiError,
    PermitContextError,
    PermitNotFoundError,
)
from permit.sync import Permit as SyncPermit
from tests.utils import ORG, PROJECT, Call, call, offline_config, sent

FLAVOURS = ["async", "sync"]
ORGANIZATION_KEY = ApiKeyAccessLevel.ORGANIZATION_LEVEL_API_KEY
PROJECT_KEY = ApiKeyAccessLevel.PROJECT_LEVEL_API_KEY
ENVIRONMENT_KEY = ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY

# The headers the SDK sets. The wait-for-sync ones are listed so that sending one shows.
HEADERS = ("Authorization", "Content-Type", "X-Wait-Timeout", "X-Timeout-Policy")
JSON_HEADERS: dict[str, str | None] = {
    "Authorization": "Bearer test-token",
    "Content-Type": "application/json",
    "X-Wait-Timeout": None,
    "X-Timeout-Policy": None,
}


class ApiError(NamedTuple):
    """An error status, the API's JSON body with it, and the error the SDK raises for it."""

    status: int
    body: dict[str, Any]
    raises: type[PermitApiError]


def error_details(error_code: str, title: str) -> dict[str, Any]:
    return {
        "id": "6a1b2c3d0000400080000000000000ee",
        "title": title,
        "error_code": error_code,
        "message": f"{title}.",
        "support_link": "https://docs.permit.io/errors",
    }


NOT_FOUND = ApiError(404, error_details("NOT_FOUND", "Not found"), PermitNotFoundError)
DUPLICATE = ApiError(
    409, error_details("DUPLICATE_ENTITY", "Already exists"), PermitAlreadyExistsError
)
FORBIDDEN = ApiError(403, error_details("FORBIDDEN_ACCESS", "Forbidden"), PermitApiDetailedError)


class Case(NamedTuple):
    """One method call, the request it must send, and what it returns.

    ``call`` is the method's dotted path under ``permit.api``, and ``key`` the narrowest API
    key level the method accepts. ``response`` is the JSON the server answers with, or None
    for an empty 204; ``model`` is what it parses into (each item's, for a list), or None
    when the method returns nothing. ``error`` is the API error the error test answers with.
    """

    call: Call
    key: ApiKeyAccessLevel
    method: str
    path: str
    query: list[tuple[str, str]]
    body: Any
    response: Any
    model: type[BaseModel] | None
    error: ApiError


TIMESTAMP = "2026-01-01T00:00:00+00:00"
ORGANIZATION_ID = "6a1b2c3d-0000-4000-8000-000000000001"
PROJECT_ID = "6a1b2c3d-0000-4000-8000-000000000002"
ENVIRONMENT_ID = "6a1b2c3d-0000-4000-8000-000000000003"
DEFAULT_PAGE = [("page", "1"), ("per_page", "100")]
SECOND_PAGE = [("page", "2"), ("per_page", "10")]

PROJECTS = "/v2/projects"
ENVS = f"{PROJECTS}/web/envs"

PROJECT_READ = {
    "key": "web",
    "name": "Web",
    "id": PROJECT_ID,
    "organization_id": ORGANIZATION_ID,
    "created_at": TIMESTAMP,
    "updated_at": TIMESTAMP,
}
ENVIRONMENT_READ = {
    "key": "dev",
    "name": "Development",
    "id": ENVIRONMENT_ID,
    "organization_id": ORGANIZATION_ID,
    "project_id": PROJECT_ID,
    "created_at": TIMESTAMP,
    "updated_at": TIMESTAMP,
}
# What the API answers a get or a list of environments with: an environment and its email
# configuration.
ENVIRONMENT_WITH_EMAIL_CONFIG = {
    **ENVIRONMENT_READ,
    "email_configuration": "6a1b2c3d-0000-4000-8000-000000000080",
}
ENVIRONMENT_STATS = {
    **ENVIRONMENT_READ,
    "pdp_configs": [
        {
            "id": "6a1b2c3d-0000-4000-8000-000000000060",
            "organization_id": ORGANIZATION_ID,
            "project_id": PROJECT_ID,
            "environment_id": ENVIRONMENT_ID,
            "client_secret": "test-client-secret",
        }
    ],
    "stats": {
        "roles": 2,
        "users": 3,
        "policies": 4,
        "resources": 1,
        "tenants": 1,
        "has_decision_logs": True,
        "members": [],
        "mau": 3,
    },
}
API_KEY = {
    "id": "6a1b2c3d-0000-4000-8000-000000000070",
    "organization_id": ORGANIZATION_ID,
    "project_id": PROJECT_ID,
    "environment_id": ENVIRONMENT_ID,
    "owner_type": "pdp_config",
    "secret": "test-api-key-secret",
    "created_at": TIMESTAMP,
}
COPY = {"target_env": {"existing": "staging"}, "conflict_strategy": "overwrite"}

CASES = {
    # projects
    "projects.list": Case(
        call=call("projects.list"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=PROJECTS,
        query=DEFAULT_PAGE,
        body=None,
        response=[PROJECT_READ],
        model=ProjectRead,
        error=FORBIDDEN,
    ),
    "projects.list-page": Case(
        call=call("projects.list", page=2, per_page=10),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=PROJECTS,
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=ProjectRead,
        error=FORBIDDEN,
    ),
    "projects.get": Case(
        call=call("projects.get", "web"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=f"{PROJECTS}/web",
        query=[],
        body=None,
        response=PROJECT_READ,
        model=ProjectRead,
        error=NOT_FOUND,
    ),
    "projects.get_by_key": Case(
        call=call("projects.get_by_key", "web"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=f"{PROJECTS}/web",
        query=[],
        body=None,
        response=PROJECT_READ,
        model=ProjectRead,
        error=NOT_FOUND,
    ),
    "projects.get_by_id": Case(
        call=call("projects.get_by_id", PROJECT_ID),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=f"{PROJECTS}/{PROJECT_ID}",
        query=[],
        body=None,
        response=PROJECT_READ,
        model=ProjectRead,
        error=NOT_FOUND,
    ),
    # The default initial environments are left for the API to create, not sent.
    "projects.create": Case(
        call=call("projects.create", {"key": "web", "name": "Web"}),
        key=ORGANIZATION_KEY,
        method="POST",
        path=PROJECTS,
        query=[],
        body={"key": "web", "name": "Web"},
        response=PROJECT_READ,
        model=ProjectRead,
        error=DUPLICATE,
    ),
    "projects.create-without-environments": Case(
        call=call("projects.create", ProjectCreate(key="web", name="Web", initial_environments=[])),
        key=ORGANIZATION_KEY,
        method="POST",
        path=PROJECTS,
        query=[],
        body={"key": "web", "name": "Web", "initial_environments": []},
        response=PROJECT_READ,
        model=ProjectRead,
        error=DUPLICATE,
    ),
    "projects.update": Case(
        call=call("projects.update", "web", {"description": "The storefront", "settings": None}),
        key=PROJECT_KEY,
        method="PATCH",
        path=f"{PROJECTS}/web",
        query=[],
        body={"description": "The storefront", "settings": None},
        response={**PROJECT_READ, "description": "The storefront"},
        model=ProjectRead,
        error=NOT_FOUND,
    ),
    "projects.delete": Case(
        call=call("projects.delete", "web"),
        key=PROJECT_KEY,
        method="DELETE",
        path=f"{PROJECTS}/web",
        query=[],
        body=None,
        response=None,
        model=None,
        error=NOT_FOUND,
    ),
    # environments
    "environments.list": Case(
        call=call("environments.list", "web"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=ENVS,
        query=DEFAULT_PAGE,
        body=None,
        response=[ENVIRONMENT_WITH_EMAIL_CONFIG],
        model=EnvironmentRead,
        error=NOT_FOUND,
    ),
    "environments.list-page": Case(
        call=call("environments.list", "web", page=2, per_page=10),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=ENVS,
        query=SECOND_PAGE,
        body=None,
        response=[],
        model=EnvironmentRead,
        error=NOT_FOUND,
    ),
    "environments.get": Case(
        call=call("environments.get", "web", "dev"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=f"{ENVS}/dev",
        query=[],
        body=None,
        response=ENVIRONMENT_WITH_EMAIL_CONFIG,
        model=EnvironmentRead,
        error=NOT_FOUND,
    ),
    "environments.get_by_key": Case(
        call=call("environments.get_by_key", "web", "dev"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=f"{ENVS}/dev",
        query=[],
        body=None,
        response=ENVIRONMENT_WITH_EMAIL_CONFIG,
        model=EnvironmentRead,
        error=NOT_FOUND,
    ),
    "environments.get_by_id": Case(
        call=call("environments.get_by_id", PROJECT_ID, ENVIRONMENT_ID),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=f"{PROJECTS}/{PROJECT_ID}/envs/{ENVIRONMENT_ID}",
        query=[],
        body=None,
        response=ENVIRONMENT_WITH_EMAIL_CONFIG,
        model=EnvironmentRead,
        error=NOT_FOUND,
    ),
    "environments.get_stats": Case(
        call=call("environments.get_stats", "web", "dev"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path=f"{ENVS}/dev/stats",
        query=[],
        body=None,
        response=ENVIRONMENT_STATS,
        model=EnvironmentStats,
        error=NOT_FOUND,
    ),
    "environments.get_api_key": Case(
        call=call("environments.get_api_key", "web", "dev"),
        key=ENVIRONMENT_KEY,
        method="GET",
        path="/v2/api-key/web/dev",
        query=[],
        body=None,
        response=API_KEY,
        model=APIKeyRead,
        error=NOT_FOUND,
    ),
    "environments.create": Case(
        call=call("environments.create", "web", {"key": "staging", "name": "Staging"}),
        key=PROJECT_KEY,
        method="POST",
        path=ENVS,
        query=[],
        body={"key": "staging", "name": "Staging"},
        response={**ENVIRONMENT_READ, "key": "staging", "name": "Staging"},
        model=EnvironmentRead,
        error=DUPLICATE,
    ),
    "environments.update": Case(
        call=call("environments.update", "web", "dev", {"name": "Dev", "description": None}),
        key=ENVIRONMENT_KEY,
        method="PATCH",
        path=f"{ENVS}/dev",
        query=[],
        body={"name": "Dev", "description": None},
        response={**ENVIRONMENT_READ, "name": "Dev"},
        model=EnvironmentRead,
        error=NOT_FOUND,
    ),
    "environments.copy": Case(
        call=call("environments.copy", "web", "dev", COPY),
        key=PROJECT_KEY,
        method="POST",
        path=f"{ENVS}/dev/copy",
        query=[],
        body=COPY,
        response={**ENVIRONMENT_READ, "key": "staging", "name": "Staging"},
        model=EnvironmentRead,
        error=DUPLICATE,
    ),
    "environments.delete": Case(
        call=call("environments.delete", "web", "dev"),
        key=ENVIRONMENT_KEY,
        method="DELETE",
        path=f"{ENVS}/dev",
        query=[],
        body=None,
        response=None,
        model=None,
        error=NOT_FOUND,
    ),
}

# The cases of the methods an environment-level key cannot call.
WIDER_KEY_CASES = {name: case for name, case in CASES.items() if case.key != ENVIRONMENT_KEY}


def scoped_config(base_url: str, key: ApiKeyAccessLevel) -> PermitConfig:
    """An offline config whose API key and SDK context are at ``key``'s level.

    ``offline_config()`` gives an environment-level key in an environment context.
    """
    config = offline_config(base_url)
    context = config.api_context
    if key is ORGANIZATION_KEY:
        context._save_api_key_accessible_scope(org=ORG)
        context.set_organization_level_context(ORG)
    elif key is PROJECT_KEY:
        context._save_api_key_accessible_scope(org=ORG, project=PROJECT)
        context.set_project_level_context(ORG, PROJECT)
    return config


async def _invoke_async(config: PermitConfig, target: Call) -> object:
    async with Permit(config) as permit:
        return await attrgetter(f"api.{target.path}")(permit)(*target.args, **target.kwargs)


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``permit.api.<target.path>`` on a new async or blocking client, then close it."""
    if flavour == "async":
        return asyncio.run(_invoke_async(config, target))
    with SyncPermit(config) as permit:
        result = attrgetter(f"api.{target.path}")(permit)(*target.args, **target.kwargs)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


def public_methods(prefix: str, api: type) -> set[str]:
    return {
        f"{prefix}.{name}"
        for name, value in vars(api).items()
        if not name.startswith("_") and callable(value)
    }


def test_every_public_method_has_a_case() -> None:
    public = public_methods("projects", ProjectsApi) | public_methods(
        "environments", EnvironmentsApi
    )

    assert {case.call.path for case in CASES.values()} == public
    assert len(public) == 17


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_request_and_response(httpserver: HTTPServer, case: Case, flavour: str) -> None:
    config = scoped_config(httpserver.url_for("").rstrip("/"), case.key)
    handler = httpserver.expect_request(case.path, method=case.method)
    if case.response is None:
        handler.respond_with_data("", status=204)
    else:
        handler.respond_with_json(case.response)

    result = invoke(config, flavour, case.call)

    assert [sent(request) for request, _ in httpserver.log] == [
        {"method": case.method, "path": case.path, "query": case.query, "body": case.body}
    ]
    assert [sent_headers(request) for request, _ in httpserver.log] == [JSON_HEADERS]
    if case.model is None:
        assert result is None
    elif isinstance(case.response, list):
        assert isinstance(result, list)
        assert [type(item) for item in result] == [case.model] * len(case.response)
        assert result == [case.model.parse_obj(item) for item in case.response]
    else:
        assert type(result) is case.model
        assert result == case.model.parse_obj(case.response)


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_an_api_error_raises_the_matching_permit_api_error(
    httpserver: HTTPServer, case: Case, flavour: str
) -> None:
    config = scoped_config(httpserver.url_for("").rstrip("/"), case.key)
    httpserver.expect_request(case.path, method=case.method).respond_with_json(
        case.error.body, status=case.error.status
    )

    with pytest.raises(PermitApiError) as raised:
        invoke(config, flavour, case.call)

    assert type(raised.value) is case.error.raises
    assert raised.value.status_code == case.error.status
    assert raised.value.details == case.error.body
    assert len(httpserver.log) == 1


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", WIDER_KEY_CASES.values(), ids=WIDER_KEY_CASES.keys())
def test_a_narrower_api_key_is_refused_before_sending(
    httpserver: HTTPServer, case: Case, flavour: str
) -> None:
    narrower = API_ACCESS_LEVELS[API_ACCESS_LEVELS.index(case.key) + 1]
    config = scoped_config(httpserver.url_for("").rstrip("/"), narrower)

    with pytest.raises(PermitContextError, match=re.escape(f"access level: {case.key}")):
        invoke(config, flavour, case.call)

    assert httpserver.log == []
