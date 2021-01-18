from typing import Optional, List, Callable, Dict, Any

from .client import authorization_client, ResourceStub
from .resource_registry import ResourceDefinition, ActionDefinition
from .enforcer import enforcer
from .markers import resource_id, resource_type, org_id
from .constants import SIDECAR_URL
from .logger import logger

def init(token, app_name, service_name, **kwargs):
    """
    inits the authorizon client
    """
    logger.info(f"authorizon.init", sidecar_url=SIDECAR_URL)
    authorization_client.initialize(
        token=token, app_name=app_name, service_name=service_name, **kwargs
    )

def resource(
    name: str,
    type: str,
    path: str,
    description: str = None,
    actions: List[ActionDefinition] = [],
    attributes: Optional[Dict[str, Any]] = None,
    **kwargs
) -> ResourceStub:
    """
    declare a resource type.

    usage:

    authorizon.resource(
        name="Todo",
        description="todo item",
        type=authorizon.types.REST,
        path="/lists/{list_id}/todos/{todo_id}",
        actions=[
            authorizon.action(
                name="add",
                title="Add",
                path="/lists/{list_id}/todos/",
                verb="post",
            ),
            ...
        ]
    )

    you can later add actions on that resource:

    todo = authorizon.resource( ... )
    todo.action(
        name="add",
        title="Add",
        path="/lists/{list_id}/todos/",
        verb="post",
    )
    """
    attributes = attributes or {}
    attributes.update(kwargs)
    resource = ResourceDefinition(
        name=name,
        type=type,
        path=path,
        description=description,
        actions=actions,
        attributes=attributes
    )
    return authorization_client.add_resource(resource)

def action(
        name: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        path: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ActionDefinition:
    """
    declare an action on a resource.

    usage:
    authorizon.resource(
        ...,
        actions = [
            authorizon.action(...),
            authorizon.action(...),
        ]
    )
    """
    attributes = attributes or {}
    attributes.update(kwargs)
    return ActionDefinition(
        name=name,
        title=title,
        description=description,
        path=path,
        attributes=attributes
    )

sync_user = authorization_client.sync_user
delete_user = authorization_client.delete_user
sync_org = authorization_client.sync_org
delete_org = authorization_client.delete_org
add_user_to_org = authorization_client.add_user_to_org
remove_user_from_org = authorization_client.remove_user_from_org
get_orgs_for_user = authorization_client.get_orgs_for_user
assign_role = authorization_client.assign_role
unassign_role = authorization_client.unassign_role
update_policy_data = authorization_client.update_policy_data

is_allowed = enforcer.is_allowed
transform_resource_context = enforcer.add_transform
provide_context = enforcer.add_context