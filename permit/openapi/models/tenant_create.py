from typing import Any, Dict, Optional

from pydantic import BaseModel, Extra, Field


class TenantCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A unique id by which Permit will identify the tenant. The tenant key must be url-friendly (slugified).",
        title="Key",
    )
    name: str = Field(
        ..., description="A descriptive name for the tenant", title="Name"
    )
    description: Optional[str] = Field(
        None,
        description="an optional longer description of the tenant",
        title="Description",
    )
    attributes: Optional[Dict[str, Any]] = Field(
        {},
        description="Arbitraty tenant attributes that will be used to enforce attribute-based access control policies.",
        title="Attributes",
    )
