from abc import ABC
from typing import Union

from permit.openapi import AuthenticatedClient
from permit.openapi.types import UNSET, Unset


class Api(ABC):
    def __init__(
        self, client: AuthenticatedClient, permit_session: Union[Unset, str] = UNSET
    ):
        self.client = client
        self.permit_session = permit_session
