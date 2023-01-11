from typing import Optional, Type, TypeVar, Union

import httpx
from pydantic import BaseModel

from permit.openapi.models import HTTPValidationError

T = TypeVar("T", bound=BaseModel)


class APIErrorDict(dict):
    ...


def parse_response(
    *, response: httpx.Response, model: Type[T]
) -> Optional[Union[T, HTTPValidationError, APIErrorDict]]:
    if response.status_code in range(200, 300):
        return model.parse_obj(response.json())
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())
        return response_422

    return APIErrorDict(response.json())
