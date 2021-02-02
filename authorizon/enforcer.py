import requests
import json
import copy

from typing import Optional, Dict, Any, Callable, Union

from .constants import SIDECAR_URL
from .resource import Resource, ResourceNotFound
from .logger import logger

def set_if_not_none(d: dict, k: str, v):
    if v is not None:
        d[k] = v

Context = Dict[str, Any]
ContextTransform = Callable[[Context], Context]
ResourceType = Union[str, Resource, Dict[str, Any]]

class Enforcer:
    POLICY_NAME = "rbac"

    def __init__(self):
        self._transforms = []
        self._context = {}

    def add_transform(self, transform: ContextTransform):
        self._transforms.append(transform)

    def add_context(self, context: Context):
        self._context.update(context)

    def _combine_context(self, query_context: Context) -> Context:
        combined_context = {}
        combined_context.update(self._context)
        combined_context.update(query_context)
        return combined_context

    def _transform_context(self, initial_context: Context) -> Context:
        context = copy.deepcopy(initial_context)
        for transform in self._transforms:
            context = transform(context)
        return context

    def _translate_resource(self, resource: ResourceType) -> Dict[str, Any]:
        resource_dict = {}
        if isinstance(resource, str):
            try:
                resource_dict = Resource.from_path(resource).dict()
            except ResourceNotFound:
                logger.warn("resource not found", resource_path=resource)
                return {}
        elif isinstance(resource, Resource):
            resource_dict = resource.dict()
        elif isinstance(resource, dict):
            resource_dict = resource
        else:
            raise ValueError("Unsupported resource type: {}".format(type(resource)))

        resource_dict['context'] = self._transform_context(resource_dict['context'])
        return resource_dict

    def is_allowed(self, user: str, action: str, resource: ResourceType, context: Context = {}) -> bool:
        """
        usage:

        authorizon.is_allowed(user, 'get', '/tasks/23')
        authorizon.is_allowed(user, 'get', '/tasks')


        authorizon.is_allowed(user, 'post', '/lists/3/todos/37', context={org_id=2})


        authorizon.is_allowed(user, 'view', task)
        authorizon.is_allowed('view', task)
        """
        resource = self._translate_resource(resource)
        if not resource:
            return False
        query_context = self._combine_context(context)
        input = {
            "user": user,
            "action": action,
            "resource": resource,
            "context": query_context,
        }
        response = requests.post(f"{SIDECAR_URL}/allowed", data=json.dumps(input))
        response_data = response.json()
        return response_data.get("allow", response_data.get("result", False))

enforcer = Enforcer()