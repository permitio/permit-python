from typing import Optional
from .resource_registry import resource_registry, ResourceDefinition

class ResourceNotFound(Exception):
    pass

class Resource:
    """
    temp resource object
    """
    def __init__(self, name: str, path: str, definition: Optional[ResourceDefinition]=None, context={}):
        self._name = name
        self._instance_path = path
        self._path = definition.path if definition else None
        self._context = context
        self._definition = definition

    def dict(self):
        return {
            "type": self._name,
            "path": self._path,
            "instance": self._instance_path,
            "context": self._context
        }

    def __repr__(self):
        return "authorizon.Resource(name={}, path={}, instance={})".format(
            self._name, self._path, self._instance_path
        )

    @classmethod
    def from_path(self, path: str):
        name, resource_def, context = resource_registry.get_resource_by_path(path)
        if name is None:
            raise ResourceNotFound()
        return Resource(name, path, resource_def, context)