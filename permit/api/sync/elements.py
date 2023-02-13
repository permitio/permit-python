from __future__ import annotations

from typing_extensions import TYPE_CHECKING

from permit.api.client import PermitApiClient
from permit.api.elements import Elements

if TYPE_CHECKING:
    from loguru import Logger

from uuid import UUID

from permit import PermitConfig
from permit.api.base import PermitBaseApi
from permit.openapi.models import UserLoginResponse
from permit.utils.sync import iscoroutine_func, async_to_sync

# TODO: Move Metaclass to different file - it's here for easy testing.
class PermitSyncApi(type):
    def __init__(self, name, bases, attrs):
        super().__init__(name, bases, attrs)

    def __new__(cls, name, bases, attrs):
        async_api_instance = PermitApiClient(config=attrs["config"])
        sync_api_instance = super().__new__(cls, name, bases, **kwargs)
        for name in dir(sync_api_instance):
            if name.startswith("_"):
                # do not monkey-patch protected or private method
                continue
            if not hasattr(async_api_instance, name):
                # ensure that the async api class has the method
                continue
            attribute = getattr(async_api_instance, name)
            if type(attribute) is type:
                # setattr(sync_api_instance, name, attribute(client=async_api_instance.client, config=config))
                continue
            if callable(attribute) and iscoroutine_func(attribute):
                # monkey-patch public method using async_to_sync decorator
                setattr(sync_api_instance, name, async_to_sync(attribute))
        return sync_api_instance

class SyncElements(PermitBaseApi, metaclass=PermitSyncApi):
    def __init__(self, config: PermitConfig, client: PermitApiClient, logger: Logger):
        super().__init__(config=config, client=client, logger=logger)


    async def login_as(
        self, user_id: str | UUID, tenant_id: str | UUID
    ) -> UserLoginResponse:
        """
        this function is monkey-patched in the __new__ method using
        async_to_sync decorator on :class:`PermitApiClient` corresponding methods
        """
        raise NotImplementedError()
