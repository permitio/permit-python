import functools

from permit.openapi.api.api_keys import get_environment_api_key
from permit.openapi.api.base import Api


class AsyncAPIKeysApi(Api):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.get_environment_api_key = functools.partial(
            get_environment_api_key.asyncio,
            client=self.client,
            permit_session=self.permit_session,
        )


class APIKeysApi(Api):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.get_environment_api_key = functools.partial(
            get_environment_api_key.sync,
            client=self.client,
            permit_session=self.permit_session,
        )
