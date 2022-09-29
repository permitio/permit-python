from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Extra, Field


class UserCreate(BaseModel):
    class Config:
        extra = Extra.forbid

    key: str = Field(
        ...,
        description="A unique id by which Permit will identify the user for permission checks. You will later pass this ID to the `permit.check()` API. You can use anything for this ID, the user email, a UUID or anything else as long as it's unique on your end. The user key must be url-friendly (slugified).",
        title="Key",
    )
    email: Optional[EmailStr] = Field(
        None,
        description="The email of the user. If synced, will be unique inside the environment.",
        title="Email",
    )
    first_name: Optional[str] = Field(
        None, description="First name of the user.", title="First Name"
    )
    last_name: Optional[str] = Field(
        None, description="Last name of the user.", title="Last Name"
    )
    attributes: Optional[Dict[str, Any]] = Field(
        {},
        description="Arbitraty user attributes that will be used to enforce attribute-based access control policies.",
        title="Attributes",
    )
