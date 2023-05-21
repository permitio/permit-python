from permit.utils.sync import SyncClass

from .permit import Permit as AsyncPermit


class Permit(AsyncPermit, metaclass=SyncClass):
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
