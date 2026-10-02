"""The routes only a container PDP serves, and the hosted cloud PDP does not.

The cloud PDP serves the decision routes (``/allowed``, ``/allowed/bulk``,
``/authorized_users``, ``/user-permissions`` and AuthZEN) and ``/health``. A container PDP
serves those too, and also ``/user-tenants``.
"""

SETUP_PDP_DOCS_LINK = "https://docs.permit.io/sdk/python/quickstart-python/#2-setup-your-pdp-policy-decision-point-container"

USE_A_CONTAINER_PDP = "Point the SDK's `pdp` setting at a container PDP to use it."


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
