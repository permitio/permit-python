from pydantic import BaseModel, Extra


class RelationsBlock(BaseModel):
    pass

    class Config:
        extra = Extra.forbid
