from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from permit.resources.registry import ActionDefinition


class ResourceConfig(BaseModel):
    name: str
    type: str
    path: str
    description: Optional[str]
    actions: Optional[ActionDefinition]
    attributes: Optional[Dict[str, Any]]

    class Config:
        arbitrary_types_allowed = True


class ActionConfig(BaseModel):
    name: str
    title: Optional[str]
    description: Optional[str]
    path: Optional[str]
    attributes: Optional[Dict[str, Any]]


# new api ---------------------------------------------------------------------
class ActionProperties(BaseModel):
    title: Optional[str]
    description: Optional[str]
    path: Optional[str]
    attributes: Optional[Dict[str, Any]]


class ResourceType(BaseModel):
    type: str
    description: Optional[str]
    attributes: Optional[Dict[str, Any]]
    actions: Dict[str, ActionProperties]


class ResourceTypes(BaseModel):
    resources: List[ResourceType]
