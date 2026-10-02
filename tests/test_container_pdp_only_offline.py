"""Offline tests for the routes only the container PDP serves (PER-16340).

The hosted cloud PDP serves the decision routes and ``/health``. It answers 404 for
``/user-tenants``, which ``get_user_tenants()`` calls, and the SDK raises that 404 as an
error that names the route and says it needs the container PDP.

Each call goes through the async and the blocking client, each closed once the call
returns. Every request is served by a local ``pytest_httpserver`` and the API context is
pre-populated, so no API key and no ``/v2/api-key/scope`` lookup are needed.
"""

import asyncio
import inspect
from operator import attrgetter

import pytest
from pytest_httpserver import HTTPServer

from permit import Permit, PermitConnectionError
from permit.config import PermitConfig
from permit.sync import Permit as SyncPermit
from tests.utils import Call, call

FLAVOURS = ["async", "sync"]
DOCS_LINK = "https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"


def invoke(config: PermitConfig, flavour: str, target: Call) -> object:
    """Call ``permit.<target.path>`` on a new async or blocking client, and close the client."""
    if flavour == "async":

        async def call_awaiting() -> object:
            async with Permit(config) as permit:
                return await attrgetter(target.path)(permit)(*target.args, **target.kwargs)

        return asyncio.run(call_awaiting())
    with SyncPermit(config) as permit:
        result = attrgetter(target.path)(permit)(*target.args, **target.kwargs)
    assert not inspect.isawaitable(result)
    return result


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_get_user_tenants_names_the_route_and_asks_for_a_container_pdp(
    httpserver: HTTPServer, config: PermitConfig, flavour: str
) -> None:
    httpserver.expect_request("/user-tenants", method="POST").respond_with_data("", status=404)

    with pytest.raises(PermitConnectionError) as raised:
        invoke(config, flavour, call("get_user_tenants", "alice"))

    assert str(raised.value) == (
        f"permit.get_user_tenants() got status code 404 from the PDP at {config.pdp}: only "
        "the container PDP serves /user-tenants, and the cloud PDP does not.\n"
        "Point the SDK's `pdp` setting at a container PDP to use it.\n"
        f"Read more about setting up the PDP at {DOCS_LINK}"
    )
