import requests
import json
import copy

from typing import Optional, Dict, Any, Callable, Union

from .constants import SIDECAR_URL
from .resource import Resource

def set_if_not_none(d: dict, k: str, v):
    if v is not None:
        d[k] = v

Context = Dict[str, str]
ContextTransform = Callable[[Context], Context]
ResourceType = Union[str, Resource, Dict[str, Any]]

class Enforcer:
    POLICY_NAME = "rbac"

    def __init__(self):
        self._transforms = []

    def add_transform(self, transform: ContextTransform):
        self._transforms.append(transform)

    def _transform_context(self, initial_context: Context) -> Context:
        context = copy.deepcopy(initial_context)
        for transform in self._transforms:
            context = transform(context)
        return context

    def _translate_resource(self, resource: ResourceType) -> Dict[str, Any]:
        resource_dict = {}
        if isinstance(resource, str):
            resource_dict = Resource.from_path(resource).dict()
        elif isinstance(resource, Resource):
            resource_dict = resource.dict()
        elif isinstance(resource, dict):
            resource_dict = resource
        else:
            raise ValueError("Unsupported resource type: {}".format(type(resource)))

        resource_dict['context'] = self._transform_context(resource_dict['context'])
        return resource_dict

    def is_allowed(self, user: str, action: str, resource: ResourceType) -> bool:
        """
        usage:

        authorizon.is_allowed(user, 'get', '/tasks/23')
        authorizon.is_allowed(user, 'get', '/tasks')


        authorizon.is_allowed(user, 'post', '/lists/3/todos/37', context={org_id=2})


        authorizon.is_allowed(user, 'view', task)
        authorizon.is_allowed('view', task)

        TODO: create comprehesive input
        TODO: currently assuming resource is a dict
        """
        resource = self._translate_resource(resource)
        input = {
            "user": user,
            "action": action,
            "resource": resource
        }
        response = requests.post(f"{SIDECAR_URL}/allowed", data=json.dumps(input))
        response_data = response.json()
        return response_data.get("result", False)

enforcer = Enforcer()