from typing import List

from pydantic import BaseModel, Field


class PDPInfoRead(BaseModel):
    pdp_ids: List[str] = Field(..., title="Pdp Ids")
