from typing import TypeVar, Optional, Union, Type

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
        response_200 = model.parse_obj(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.parse_obj(response.json())
        return response_422

    return APIErrorDict(response.json())
