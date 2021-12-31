from typing import NamedTuple
from typing import Optional, Dict, List, Any

from .registry import ActionDefinition


class ResourceConfig(NamedTuple):
    name: str
    type: str
    path: str
    description: Optional[str]
    actions: Optional[ActionDefinition]
    attributes: Optional[Dict[str, Any]]


class ActionConfig(NamedTuple):
    name: str
    title: Optional[str]
    description: Optional[str]
    path: Optional[str]
    attributes: Optional[Dict[str, Any]]


# new api ---------------------------------------------------------------------
class ActionProperties(NamedTuple):
    title: Optional[str]
    description: Optional[str]
    path: Optional[str]
    attributes: Optional[Dict[str, Any]]


class ResourceType(NamedTuple):
    type: str
    description: Optional[str]
    attributes: Optional[Dict[str, Any]]
    actions: Dict[str, ActionProperties]


class ResourceTypes(NamedTuple):
    resources: List[ResourceType]
