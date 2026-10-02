"""Tell the hosted cloud PDP from a container PDP, for the routes only a container PDP serves.

The cloud PDP serves the decision routes (``/allowed``, ``/allowed/bulk``,
``/authorized_users``, ``/user-permissions`` and AuthZEN) and ``/health``. A container PDP
serves those too, and also the routes the cloud PDP does not: ``/user-tenants``, the
``/local`` routes of ``permit.pdp_api``, and the ``/facts`` routes that
``proxy_facts_via_pdp`` sends the facts methods of ``permit.api`` to.

The cloud PDP answers a route it does not serve with a 404 that has an empty body. A
container PDP's own 404 has a JSON body, and so does the API's 404 that its ``/facts``
routes pass on, such as for a tenant that does not exist.
"""

from http import HTTPStatus

import aiohttp
from yarl import URL

CLOUD_PDP_HOST = "cloudpdp.api.permit.io"
"""The host of the hosted cloud PDP."""

SETUP_PDP_DOCS_LINK = "https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"

USE_A_CONTAINER_PDP = "Point the SDK's `pdp` setting at a container PDP to use it."
USE_A_CONTAINER_PDP_FOR_FACTS = (
    "Point the SDK's `pdp` setting at a container PDP to use it, or turn proxy_facts_via_pdp "
    "off to send facts to the Permit REST API."
)


def is_cloud_pdp(pdp_url: str) -> bool:
    """Whether ``pdp_url`` is the address of the hosted cloud PDP.

    Args:
        pdp_url: A PDP address, as the SDK's ``pdp`` setting takes it.

    Returns:
        True if the URL's host is the cloud PDP's, whatever its scheme, port or path.
    """
    try:
        host = URL(pdp_url).host
    except ValueError:
        return False
    return host == CLOUD_PDP_HOST


async def is_cloud_pdp_route_not_found(response: aiohttp.ClientResponse, pdp_url: str) -> bool:
    """Whether a PDP's ``response`` is the cloud PDP's 404 for a route it does not serve.

    It is when the status is 404 and either ``pdp_url`` is the cloud PDP's address or the
    body is empty, which is how the cloud PDP answers such a route. A 404 with a body comes
    from a container PDP, or from the API through a container PDP's ``/facts`` routes, and
    is a real "not found".

    Args:
        response: The PDP's response to a request for a route only the container PDP serves.
        pdp_url: The address of the PDP the request was sent to, as the SDK's ``pdp``
            setting gives it.

    Returns:
        True if the response is the cloud PDP's 404 for a route it does not serve.
    """
    if response.status != HTTPStatus.NOT_FOUND:
        return False
    if is_cloud_pdp(pdp_url):
        return True
    return not (await response.read()).strip()


def container_pdp_only_message(
    caller: str, route: str, pdp_url: str, advice: str = USE_A_CONTAINER_PDP
) -> str:
    """The error message for a route only the container PDP serves, that a PDP answered 404.

    Args:
        caller: What sent the request, such as ``permit.get_user_tenants()``.
        route: The route the PDP answered 404 for, such as ``/user-tenants``.
        pdp_url: The address of that PDP, as the SDK's ``pdp`` setting gives it.
        advice: What to do instead.

    Returns:
        The message, which names the route and says that it needs the container PDP.
    """
    return (
        f"{caller} got status code 404 from the PDP at {pdp_url}: only the container PDP "
        f"serves {route}, and the cloud PDP does not.\n"
        f"{advice}\n"
        f"Read more about setting up the PDP at {SETUP_PDP_DOCS_LINK}"
    )
