import pytest
from permit import Permit
import asyncio
from permit.enforcement.enforcer import Action, Resource, User, Context, PermitConnectionError


PERMIT_TOKEN=""
PERMIT_PDP_URL=""
PERMIT_DEBUG_MODE=True

@pytest.mark.asyncio
async def test_permit_check_raises_exception_when_no_connection():
    """
    Check permit enforcer and exceptions
    """
    # init permit
    permit_client = Permit(PERMIT_TOKEN, PERMIT_PDP_URL, PERMIT_DEBUG_MODE)
    # check
    with pytest.raises(PermitConnectionError):
        await permit_client.check("testUserID", "action", "resource")
