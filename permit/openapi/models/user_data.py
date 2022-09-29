from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class UserData(BaseModel):
    roleAssignments: Optional[Dict[str, List[str]]] = Field(
        None, title="Roleassignments"
    )
    attributes: Optional[Dict[str, Union[str, int, bool]]] = Field(
        None, title="Attributes"
    )
