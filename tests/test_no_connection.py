import asyncio

import pytest

from permit import Permit
from permit.enforcement.enforcer import Action, Context, Resource, User
from permit.exceptions import PermitException

PERMIT_TOKEN = ""
PERMIT_PDP_URL = ""
PERMIT_DEBUG_MODE = True


async def test_permit_check_raises_exception_when_no_connection():
    """
    Check permit enforcer and exceptions
    """
    # init permit
    permit_client = Permit(PERMIT_TOKEN, PERMIT_PDP_URL, PERMIT_DEBUG_MODE)
    # check
    with pytest.raises(PermitException):
        await permit_client.check("testUserID", "action", "resource")
