"""permit.api.pdps.refresh() against the Permit API (PER-16337).

``refresh()`` asks Permit to make every PDP of the environment the API key belongs to fetch
its data again. Every environment has at least one PDP configuration, and the call returns
once Permit has sent the refresh, so these tests check what it returns, not what the PDPs
do with it. The tests create nothing, so there is nothing to tear down.
"""

from uuid import UUID

import pytest

from permit import Permit
from permit.api.models import PDPDataRefreshResponse
from permit.sync import Permit as SyncPermit

pytestmark = pytest.mark.e2e


async def test_refresh_returns_a_new_update_for_the_environments_pdps(permit: Permit) -> None:
    first = await permit.api.pdps.refresh(reason="permit-python e2e")
    second = await permit.api.pdps.refresh()

    for refreshed in (first, second):
        assert type(refreshed) is PDPDataRefreshResponse
        assert isinstance(refreshed.update_id, UUID)
        assert refreshed.pdp_ids
        assert len(set(refreshed.pdp_ids)) == len(refreshed.pdp_ids)
    # Each call sends an update of its own, to the same PDP configurations.
    assert first.update_id != second.update_id
    assert set(first.pdp_ids) == set(second.pdp_ids)


def test_the_blocking_client_refreshes_the_pdps(sync_permit: SyncPermit) -> None:
    refreshed = sync_permit.api.pdps.refresh(reason="permit-python e2e, blocking client")

    assert type(refreshed) is PDPDataRefreshResponse
    assert refreshed.pdp_ids
