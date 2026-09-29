"""The script in v2_app/app/sync_app.py, migrated to permit 3.0.0."""

from typing import Any, Dict, List
from uuid import UUID

from permit.sync import Permit as SyncPermit

client = SyncPermit(token="permit_key_example", pdp="http://localhost:7766")


def who_can_read(document: str) -> List[str]:
    result = client.authorized_users("read", f"document:{document}")
    return list(result.users)


def permissions(user: str) -> Dict[str, Any]:
    return client.get_user_permissions(user)


def visible(user: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return client.filter_objects(user, "read", {}, documents)


def role_keys() -> List[str]:
    return [role.key for role in client.api.roles.list()]


def login(user_id: UUID, tenant_id: UUID) -> object:
    return client.elements.login_as(user_id, tenant_id)
