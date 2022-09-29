from typing import List, Optional

from pydantic import BaseModel, Extra, Field, conint

from permit.openapi.models.user_read import UserRead


class PaginatedResultUserRead(BaseModel):
    class Config:
        extra = Extra.forbid

    data: List[UserRead] = Field(..., title="Data")
    total_count: conint(ge=0) = Field(..., title="Total Count")
    page_count: Optional[conint(ge=0)] = Field(0, title="Page Count")
