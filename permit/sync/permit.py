from distutils.log import debug
from typing import Dict, List

from permit.constants import DEFAULT_PDP_URL
from permit.enforcement.enforcer import Action, Resource, User
from permit.mutations.client import ReadOperation, WriteOperation
from permit.resources.interfaces import ResourceConfig, ResourceTypes
from permit.resources.reporter import ResourceStub
from permit.utils.context import Context

from .client import Permit as AsyncPermit
from .utils.sync import run_sync


class Permit(AsyncPermit):
    def __init__(
        self,
        token: str,
        pdp: str = DEFAULT_PDP_URL,
        debug_mode: bool = False,
        **options,
    ):
        super().__init__(token=token, pdp=pdp, debug_mode=debug_mode, **options)

    def check(
        self,
        user: User,
        action: Action,
        resource: Resource,
        context: Context = {},
    ) -> bool:
        return run_sync(
            super().check(user=user, action=action, resource=resource, context=context)
        )

    def resource(self, config: ResourceConfig) -> ResourceStub:
        return run_sync(super().resource(config=config))

    def sync_resources(self, config: ResourceTypes) -> List[ResourceStub]:
        return run_sync(super().sync_resources(config=config))

    def read(self, *operations: ReadOperation) -> List[Dict]:
        return run_sync(super().read(*operations))

    def write(self, *operations: WriteOperation) -> List[Dict]:
        return run_sync(super().write(*operations))
