from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RoleData(BaseModel):
    grants: Optional[Dict[str, List[str]]] = Field(None, title="Grants")
