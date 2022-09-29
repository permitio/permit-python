from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Extra, Field


class UserUpdate(BaseModel):
    class Config:
        extra = Extra.forbid

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
