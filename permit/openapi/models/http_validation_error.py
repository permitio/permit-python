from typing import List, Optional

from pydantic import BaseModel, Field

from permit.openapi.models.validation_error import ValidationError


class HTTPValidationError(BaseModel):
    detail: Optional[List[ValidationError]] = Field(None, title="Detail")
