from uuid import UUID

from pydantic import BaseModel, Extra, Field


class APIKeyRead(BaseModel):
    class Config:
        extra = Extra.forbid

    id: UUID = Field(..., title="Id")
    secret: str = Field(..., title="Secret")
