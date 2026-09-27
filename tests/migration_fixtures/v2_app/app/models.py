"""Reads audit logs, relationship tuples and SDK models, written against permit 2.x."""

from typing import Any, Dict, List

from permit import AuditLogModel, Engine, Permit, PermitConfig
from permit.api.elements import LoginAsErrorMessages
from permit.api.models import RelationshipTupleRead, UserRead

permit = Permit(token="permit_key_example")
EXPECTED_HEADER = f"bearer {PermitConfig(token='permit_key_example').token}"


def config_id(raw: Dict[str, Any]) -> str:
    log = AuditLogModel.parse_obj(raw)
    return log.pdp_config_id.hex


def engine_name(raw: Dict[str, Any]) -> str:
    engine = AuditLogModel.parse_obj(raw).engine
    return "opa" if engine == Engine.OPA else "avp"


def parse_user(raw: Dict[str, Any]) -> UserRead:
    return UserRead.model_validate(raw)


def user_fields() -> List[str]:
    return list(UserRead.model_fields)


def tuple_ids(tuples: List[RelationshipTupleRead]) -> List[str]:
    return [t.object_id.hex for t in tuples]


async def all_tuples() -> List[RelationshipTupleRead]:
    return await permit.api.relationship_tuples.list()


def not_found(message: str) -> bool:
    return message == LoginAsErrorMessages.USER_NOT_FOUND.value


def user_dict(user: UserRead) -> Dict[str, Any]:
    return user.model_dump()
