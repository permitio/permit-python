"""The readers in v2_app/app/models.py, migrated to permit 3.0.0."""

from typing import Any, Dict, List

from permit import AuditLogModel, Engine, Permit, PermitConfig
from permit.api.models import RelationshipTupleRead, UserRead

permit = Permit(token="permit_key_example")
EXPECTED_HEADER = f"Bearer {PermitConfig(token='permit_key_example').token}"
USER_NOT_FOUND = "User not found"


def config_id(raw: Dict[str, Any]) -> str:
    log = AuditLogModel.parse_obj(raw)
    return log.pdp_config_id.hex if log.pdp_config_id is not None else ""


def engine_name(raw: Dict[str, Any]) -> str:
    engine = AuditLogModel.parse_obj(raw).engine
    if engine == Engine.GENERIC:
        return "generic"
    return "opa" if engine == Engine.OPA else "avp"


def parse_user(raw: Dict[str, Any]) -> UserRead:
    return UserRead.parse_obj(raw)


def user_fields() -> List[str]:
    return list(UserRead.__fields__)


def tuple_ids(tuples: List[RelationshipTupleRead]) -> List[str]:
    return [t.object_id.hex for t in tuples if t.object_id is not None]


async def all_tuples() -> List[RelationshipTupleRead]:
    return await permit.api.relationship_tuples.list()


def not_found(message: str) -> bool:
    return message == USER_NOT_FOUND


def user_dict(user: UserRead) -> Dict[str, Any]:
    return user.dict()
