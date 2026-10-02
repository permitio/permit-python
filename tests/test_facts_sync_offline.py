"""Offline tests for the proxied facts requests the PDP waits on before it answers.

With ``proxy_facts_via_pdp`` on, the SDK sends its facts requests to the PDP, with the
``X-Wait-Timeout`` header when a facts sync timeout is set (PER-16681). The PDP waits on
some of its facts routes only, and forwards the others without waiting (PER-16339). These
tests pin the request every facts method sends, and so which of them the PDP waits on.

Each call goes through the async and the blocking client, and the test checks the request
it puts on the wire (method, path, query string, headers and JSON body). Every request is
served by a local ``pytest_httpserver``, the API and the PDP each on a server of their own,
and the API context is pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are
needed.
"""

import asyncio
import inspect
import json
import re
from collections.abc import Callable
from contextlib import nullcontext
from operator import attrgetter
from pathlib import Path
from typing import Any

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request

from permit import Permit
from permit.config import PermitConfig
from permit.sync import Permit as SyncPermit
from tests.facts_methods import ALIASES, CASES, FACTS_APIS, USER, Case, on_pdp
from tests.utils import FACTS, Call, call, offline_config, sent

FLAVOURS = ["async", "sync"]

HEADERS = ("Authorization", "Content-Type", "X-Wait-Timeout", "X-Timeout-Policy")

REPO_ROOT = Path(__file__).resolve().parents[1]
PDP_SPEC = REPO_ROOT / ".github" / "api-specs" / "pdp.json"

CREATE_USER = call("api.users.create", {"key": "alice"})
CREATE_USER_SENT = {"method": "POST", "path": "/facts/users", "query": [], "body": {"key": "alice"}}


@pytest.fixture
def pdp_server(httpserver_ipv4: HTTPServer) -> HTTPServer:
    """A server of its own for the PDP, so a request reaching it is told from one to the API."""
    return httpserver_ipv4


def make_config(api: HTTPServer, pdp: HTTPServer, **options: Any) -> PermitConfig:
    """An offline config for the API on ``api`` and the PDP on ``pdp``, with ``options``.

    The options go to ``PermitConfig`` itself, which validates them as it does for an
    application that passes them.
    """
    offline = offline_config(api.url_for("").rstrip("/"))
    return PermitConfig(
        token=offline.token,
        api_url=offline.api_url,
        pdp=pdp.url_for("").rstrip("/"),
        api_context=offline.api_context,
        **options,
    )


async def _invoke_async(config: PermitConfig, target: Call, wait: dict[str, Any] | None) -> object:
    async with Permit(config) as permit:
        with nullcontext(permit) if wait is None else permit.wait_for_sync(**wait) as client:
            return await attrgetter(target.path)(client)(*target.args, **target.kwargs)


def invoke(
    config: PermitConfig, flavour: str, target: Call, wait: dict[str, Any] | None = None
) -> object:
    """Call ``permit.<target.path>`` on the async or the blocking client, then close it.

    With ``wait``, the call goes through the client ``permit.wait_for_sync(**wait)`` yields.
    """
    if flavour == "async":
        return asyncio.run(_invoke_async(config, target, wait))
    with (
        SyncPermit(config) as permit,
        nullcontext(permit) if wait is None else permit.wait_for_sync(**wait) as client,
    ):
        result = attrgetter(target.path)(client)(*target.args, **target.kwargs)
    assert not inspect.isawaitable(result)
    return result


def sent_headers(request: Request) -> dict[str, str | None]:
    return {name: request.headers.get(name) for name in HEADERS}


def facts_headers(wait_timeout: str | None, policy: str | None) -> dict[str, str | None]:
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json",
        "X-Wait-Timeout": wait_timeout,
        "X-Timeout-Policy": policy,
    }


# --- the timeout in the config ---------------------------------------------------------

# PermitConfig validates facts_sync_timeout as a float, so an int is sent as "3.0".
CONFIG_TIMEOUTS = {
    "unset": (None, None),
    "zero": (0, "0.0"),
    "zero-float": (0.0, "0.0"),
    "int": (3, "3.0"),
    "float": (2.5, "2.5"),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("timeout", "header"), CONFIG_TIMEOUTS.values(), ids=CONFIG_TIMEOUTS.keys()
)
def test_facts_sync_timeout_is_sent_unless_it_is_none(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    timeout: float | None,
    header: str | None,
    flavour: str,
) -> None:
    """0 is sent too, so the PDP answers without waiting instead of waiting its default."""
    config = make_config(
        httpserver, pdp_server, proxy_facts_via_pdp=True, facts_sync_timeout=timeout
    )
    pdp_server.expect_request("/facts/users", method="POST").respond_with_json(USER)

    invoke(config, flavour, CREATE_USER)

    [(request, _)] = pdp_server.log
    assert sent(request) == CREATE_USER_SENT
    assert sent_headers(request) == facts_headers(header, None)
    assert httpserver.log == []


# --- the timeout of wait_for_sync() ---------------------------------------------------

# wait_for_sync() sets the timeout it is given on its client's config as it is, so an int
# is sent as "3". Its own timeout replaces the config's, 0 included; its policy replaces
# the config's only when it is given.
WAIT_FOR_SYNC_TIMEOUTS = {
    "default": ({}, "10.0", "fail"),
    "zero": ({"timeout": 0}, "0", "fail"),
    "zero-float": ({"timeout": 0.0}, "0.0", "fail"),
    "int": ({"timeout": 3}, "3", "fail"),
    "float": ({"timeout": 2.5}, "2.5", "fail"),
    "zero-policy": ({"timeout": 0, "policy": "ignore"}, "0", "ignore"),
}


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize(
    ("wait", "header", "policy"),
    WAIT_FOR_SYNC_TIMEOUTS.values(),
    ids=WAIT_FOR_SYNC_TIMEOUTS.keys(),
)
def test_wait_for_sync_sends_its_timeout_even_when_it_is_zero(
    *,
    httpserver: HTTPServer,
    pdp_server: HTTPServer,
    wait: dict[str, Any],
    header: str,
    policy: str,
    flavour: str,
) -> None:
    config = make_config(
        httpserver,
        pdp_server,
        proxy_facts_via_pdp=True,
        facts_sync_timeout=7.5,
        facts_sync_timeout_policy="fail",
    )
    pdp_server.expect_request("/facts/users", method="POST").respond_with_json(USER)

    invoke(config, flavour, CREATE_USER, wait)

    [(request, _)] = pdp_server.log
    assert sent(request) == CREATE_USER_SENT
    assert sent_headers(request) == facts_headers(header, policy)
    assert httpserver.log == []


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_without_proxy_facts_via_pdp_a_zero_timeout_sends_no_header(
    httpserver: HTTPServer, pdp_server: HTTPServer, flavour: str
) -> None:
    """The facts request goes to the API, which does not wait, so nothing tells it to."""
    config = make_config(
        httpserver, pdp_server, facts_sync_timeout=0, facts_sync_timeout_policy="fail"
    )
    httpserver.expect_request(f"{FACTS}/users", method="POST").respond_with_json(USER)

    invoke(config, flavour, CREATE_USER)

    [(request, _)] = httpserver.log
    assert sent(request) == {**CREATE_USER_SENT, "path": f"{FACTS}/users"}
    assert sent_headers(request) == facts_headers(None, None)
    assert pdp_server.log == []


# --- which facts methods the PDP waits on (PER-16339) ---------------------------------

# The facts routes the container PDP waits on before it answers: until the change is in its
# own data, or for as long as X-Wait-Timeout says. It forwards every other /facts request
# to the API without waiting (PER-16338 asks it to wait on more). These are also the only
# /facts operations the PDP's OpenAPI spec lists: it leaves out the routes it forwards
# without waiting. test_the_synced_routes_are_the_facts_operations_of_the_pdp_spec keeps
# this set and the committed copy of that spec in step.
SYNCED_ROUTES = frozenset(
    {
        "POST /facts/users",
        "PUT /facts/users/{user_id}",
        "PATCH /facts/users/{user_id}",
        "POST /facts/users/{user_id}/roles",
        "DELETE /facts/users/{user_id}/roles",
        "POST /facts/tenants",
        "POST /facts/role_assignments",
        "DELETE /facts/role_assignments",
        "POST /facts/resource_instances",
        "PATCH /facts/resource_instances/{instance_id}",
        "POST /facts/relationship_tuples",
    }
)


def route_matches(route: str, method: str, path: str) -> bool:
    """Whether a request for ``method`` and ``path`` is one for ``route``."""
    route_method, template = route.split(" ")
    pattern = re.sub(r"\{[^/{}]+\}", "[^/]+", template)
    return route_method == method and re.fullmatch(pattern, path) is not None


def test_every_public_facts_method_has_a_case() -> None:
    public = {
        f"{api}.{name}"
        for api, api_class in FACTS_APIS.items()
        for name, value in vars(api_class).items()
        if not name.startswith("_") and callable(value)
    }

    assert set(CASES) == public - set(ALIASES)
    assert set(ALIASES.values()) <= set(CASES)


def test_the_synced_routes_are_the_facts_operations_of_the_pdp_spec() -> None:
    """A refreshed PDP spec that lists another /facts route means the PDP may wait on it."""
    spec = json.loads(PDP_SPEC.read_text(encoding="utf-8"))
    facts_operations = {
        f"{method.upper()} {path}"
        for path, operations in spec["paths"].items()
        if path.startswith("/facts/")
        for method in operations
    }

    assert facts_operations == SYNCED_ROUTES


def test_every_synced_route_is_the_route_of_a_case() -> None:
    """So a case for a synced route spells it as SYNCED_ROUTES does, and counts as waiting."""
    assert {case.route for case in CASES.values()} >= SYNCED_ROUTES


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_a_proxied_facts_method_sends_the_sync_headers_to_its_route(
    *, httpserver: HTTPServer, pdp_server: HTTPServer, case: Case, flavour: str
) -> None:
    """Every facts request carries X-Wait-Timeout; the PDP waits only on SYNCED_ROUTES."""
    config = make_config(
        httpserver,
        pdp_server,
        proxy_facts_via_pdp=True,
        facts_sync_timeout=2.5,
        facts_sync_timeout_policy="fail",
    )
    server, other = (pdp_server, httpserver) if on_pdp(case) else (httpserver, pdp_server)
    handler = server.expect_request(case.path, method=case.method)
    if case.response is None:
        handler.respond_with_data("", status=204)
    else:
        handler.respond_with_json(case.response)

    invoke(config, flavour, case.call)

    [(request, _)] = server.log
    assert route_matches(case.route, request.method, request.path)
    assert sent(request) == case.request
    assert sent_headers(request) == facts_headers("2.5", "fail")
    assert other.log == []


# --- the documented lists of the methods the PDP waits on ------------------------------

# The facts methods whose request goes to a route the PDP waits on, and the writes whose
# request goes to one it forwards without waiting, as the cases above pin them.
WAITING = frozenset(
    name for name, case in CASES.items() if on_pdp(case) and case.route in SYNCED_ROUTES
)
FORWARDED_WRITES = frozenset(
    name
    for name, case in CASES.items()
    if on_pdp(case) and case.route not in SYNCED_ROUTES and not case.route.startswith("GET ")
)

# Each documented list of the methods the PDP waits on ends with this phrase. A facts
# method named after it is one the PDP does not wait on.
FORWARDED = "forwards every other facts request without waiting"
READ_YOUR_WRITES = "Read-your-writes through the PDP"


def readme_section(title: str) -> str:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    _, found, rest = readme.partition(f"\n## {title}\n")
    assert found, f"README.md has no section {title!r}"
    return rest.split("\n## ", 1)[0]


def config_description(field: str) -> str | None:
    description: str | None = PermitConfig.__fields__[field].field_info.description
    return description


# Where the methods the PDP waits on are listed, and how to read the text that lists them.
DOCUMENTED: dict[str, Callable[[], str | None]] = {
    "readme": lambda: readme_section(READ_YOUR_WRITES),
    "wait_for_sync": lambda: inspect.getdoc(Permit.wait_for_sync),
    "proxy_facts_via_pdp": lambda: config_description("proxy_facts_via_pdp"),
    "facts_sync_timeout": lambda: config_description("facts_sync_timeout"),
}


def facts_methods(text: str) -> set[str]:
    """The facts methods ``text`` names as "<api>.<method>()", as "<api>.<method>"."""
    return {
        f"{api}.{method}"
        for api, method in re.findall(r"(\w+)\.(\w+)\(\)", text)
        if api in FACTS_APIS
    }


@pytest.mark.parametrize("where", DOCUMENTED)
def test_the_docs_list_the_methods_the_pdp_waits_on(where: str) -> None:
    """Each list names the methods whose route the PDP waits on, and those alone."""
    text = DOCUMENTED[where]()
    assert text is not None
    assert text.count(FORWARDED) == 1, f"{where} does not say {FORWARDED!r} once"
    waiting, _, forwarded = text.partition(FORWARDED)

    assert facts_methods(waiting) == WAITING
    assert not facts_methods(forwarded) & WAITING


def test_the_readme_lists_the_writes_the_pdp_does_not_wait_on() -> None:
    _, _, forwarded = readme_section(READ_YOUR_WRITES).partition(FORWARDED)

    assert facts_methods(forwarded) >= FORWARDED_WRITES
