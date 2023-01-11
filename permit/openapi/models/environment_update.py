from typing import Optional

from pydantic import BaseModel, Extra, Field


class EnvironmentUpdate(BaseModel):
    class Config:
        extra = Extra.ignore

    name: Optional[str] = Field(
        None, description='The name of the environment', title='Name'
    )
    description: Optional[str] = Field(
        None,
        description='an optional longer description of the environment',
        title='Description',
    )
    custom_branch_name: Optional[str] = Field(
        None,
        description='when using gitops feature, an optional branch name for the environment',
        title='Custom Branch Name',
    )
