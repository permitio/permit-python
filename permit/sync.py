import asyncio
from distutils.log import debug
from typing import List

from permit.constants import DEFAULT_PDP_URL
from permit.enforcement.enforcer import Action, Resource, User
from permit.resources.interfaces import ResourceConfig, ResourceTypes
from permit.resources.reporter import ResourceStub
from permit.utils.context import Context

from .client import Permit as AsyncPermit
from .mutations.sync import PermitApiClient


class Permit(AsyncPermit):
    def __init__(
        self,
        token: str,
        pdp: str = DEFAULT_PDP_URL,
        debug_mode: bool = False,
        **options,
    ):
        super().__init__(token=token, pdp=pdp, debug_mode=debug_mode, **options)
        # use sync mutations client instead of async version
        self._mutations_client = PermitApiClient(self._config)

    def check(
        self,
        user: User,
        action: Action,
        resource: Resource,
        context: Context = {},
    ) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # there is no running event loop, so it's safe to use `asyncio.run`
            return asyncio.run(
                super().check(
                    user=user, action=action, resource=resource, context=context
                )
            )
        else:
            # there *is* a running event loop, so use `loop.run_until_complete`
            return loop.run_until_complete(
                super().check(
                    user=user, action=action, resource=resource, context=context
                )
            )

    def resource(self, config: ResourceConfig) -> ResourceStub:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # there is no running event loop, so it's safe to use `asyncio.run`
            return asyncio.run(super().resource(config=config))
        else:
            # there *is* a running event loop, so use `loop.run_until_complete`
            return loop.run_until_complete(super().resource(config=config))

    def sync_resources(self, config: ResourceTypes) -> List[ResourceStub]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # there is no running event loop, so it's safe to use `asyncio.run`
            return asyncio.run(super().sync_resources(config=config))
        else:
            # there *is* a running event loop, so use `loop.run_until_complete`
            return loop.run_until_complete(super().sync_resources(config=config))
