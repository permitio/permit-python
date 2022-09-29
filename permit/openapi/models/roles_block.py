from pydantic import BaseModel, Extra


class RolesBlock(BaseModel):
    pass

    class Config:
        extra = Extra.forbid
