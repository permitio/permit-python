"""Offline tests: the audit-log models accept the decision logs the API returns (PER-14375).

The API no longer guarantees a ``pdp_config_id`` on a decision log, may leave out
``objects`` on a detailed log, and now stores logs from a ``GENERIC`` decision-log
engine next to the OPA and AVP ones. These tests parse those payload shapes directly;
no API key, PDP or network is involved.
"""

from typing import Any
from uuid import UUID

import pytest

from permit.api.models import (
    AuditLogModel,
    AVPEngineDecisionLog,
    DetailedAuditLogModel,
    DummyEngineModel,
    Engine,
    GenericEngineDecisionLog,
    LimitedPaginatedResultAuditLogModel,
    OPAEngineDecisionLog,
)

TIMESTAMP = "2026-01-01T12:00:00+00:00"
LOG_ID = UUID("00000000-0000-4000-8000-000000000001")
ORG_ID = UUID("00000000-0000-4000-8000-000000000002")
PROJECT_ID = UUID("00000000-0000-4000-8000-000000000003")
ENV_ID = UUID("00000000-0000-4000-8000-000000000004")
PDP_CONFIG_ID = UUID("00000000-0000-4000-8000-000000000005")
DECISION_ID = UUID("00000000-0000-4000-8000-000000000006")

OPA_RAW_DATA = {
    "engine": "OPA",
    "decision_id": str(DECISION_ID),
    "labels": {"id": str(PDP_CONFIG_ID), "version": "0.7.0"},
    "timestamp": TIMESTAMP,
    "path": "permit/root",
    "input": {"user": {"key": "alice"}, "action": "read", "resource": {"type": "document"}},
    "result": {"allow": True},
    "metrics": {"timer_rego_query_eval_ns": 1000},
}
AVP_RAW_DATA = {
    "engine": "AVP",
    "timestamp": TIMESTAMP,
    "tenant": "default",
    "input": {"principal": "alice"},
    "result": {"decision": "ALLOW"},
}
GENERIC_RAW_DATA = {
    "engine": "GENERIC",
    "timestamp": TIMESTAMP,
    "decision": True,
    "decision_id": str(DECISION_ID),
    "user_key": "alice",
    "action": "read",
    "resource_type": "document",
    "tenant": "default",
    "input": {"source": "custom-integration"},
}

pdp_config_id_missing = pytest.mark.parametrize(
    "pdp_config_id_field",
    [{"pdp_config_id": None}, {}],
    ids=["null", "absent"],
)


def audit_log(**fields: Any) -> dict:
    """An audit-log list item as the API returns it, with a known pdp_config_id by default."""
    return {
        "id": str(LOG_ID),
        "timestamp": TIMESTAMP,
        "org_id": str(ORG_ID),
        "project_id": str(PROJECT_ID),
        "env_id": str(ENV_ID),
        "pdp_config_id": str(PDP_CONFIG_ID),
        "user_key": "alice",
        "action": "read",
        "resource_type": "document",
        "tenant": "default",
        "decision": True,
        **fields,
    }


def detailed_audit_log(raw_data: dict, **fields: Any) -> dict:
    """A detailed audit log as the API returns it, with ``objects`` present by default."""
    return audit_log(raw_data=raw_data, objects={}, **fields)


def without(payload: dict, key: str) -> dict:
    return {k: v for k, v in payload.items() if k != key}


@pdp_config_id_missing
def test_audit_log_parses_without_pdp_config_id(pdp_config_id_field: dict):
    payload = {**without(audit_log(), "pdp_config_id"), **pdp_config_id_field}

    log = AuditLogModel.parse_obj(payload)

    assert log.pdp_config_id is None
    assert log.id == LOG_ID


@pdp_config_id_missing
def test_detailed_audit_log_parses_without_pdp_config_id(pdp_config_id_field: dict):
    payload = {**without(detailed_audit_log(OPA_RAW_DATA), "pdp_config_id"), **pdp_config_id_field}

    log = DetailedAuditLogModel.parse_obj(payload)

    assert log.pdp_config_id is None
    assert isinstance(log.raw_data, OPAEngineDecisionLog)


@pdp_config_id_missing
def test_audit_log_page_parses_items_without_pdp_config_id(pdp_config_id_field: dict):
    page = LimitedPaginatedResultAuditLogModel.parse_obj(
        {
            "data": [
                {**without(audit_log(), "pdp_config_id"), **pdp_config_id_field},
                audit_log(id="00000000-0000-4000-8000-000000000007"),
            ],
            "total_count": 2,
            "page_count": 1,
            "pagination_count": 2,
        }
    )

    assert [log.pdp_config_id for log in page.data] == [None, PDP_CONFIG_ID]


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AuditLogModel, audit_log(raw_data=GENERIC_RAW_DATA)),
        (DetailedAuditLogModel, detailed_audit_log(GENERIC_RAW_DATA)),
    ],
    ids=["list", "detailed"],
)
def test_audit_logs_parse_a_generic_engine_log(model: type, payload: dict):
    log = model.parse_obj(payload)

    assert isinstance(log.raw_data, GenericEngineDecisionLog)
    assert log.raw_data.engine == Engine.GENERIC
    assert log.raw_data.decision is True
    assert log.raw_data.decision_id == DECISION_ID
    assert log.raw_data.user_key == "alice"


def test_detailed_audit_log_parses_without_objects():
    payload = without(detailed_audit_log(OPA_RAW_DATA), "objects")

    log = DetailedAuditLogModel.parse_obj(payload)

    assert log.id == LOG_ID
    assert isinstance(log.raw_data, OPAEngineDecisionLog)


@pytest.mark.parametrize(
    ("raw_data", "engine_log_type"),
    [(OPA_RAW_DATA, OPAEngineDecisionLog), (AVP_RAW_DATA, AVPEngineDecisionLog)],
    ids=["opa", "avp"],
)
def test_detailed_audit_log_keeps_parsing_opa_and_avp_logs(raw_data: dict, engine_log_type: type):
    """Adding the GENERIC engine must not change how existing engine logs parse."""
    log = DetailedAuditLogModel.parse_obj(detailed_audit_log(raw_data))

    assert type(log.raw_data) is engine_log_type
    assert log.pdp_config_id == PDP_CONFIG_ID


@pytest.mark.parametrize("engine", ["OPA", "AVP"])
def test_generic_engine_log_does_not_take_other_engines_logs(engine: str):
    """An OPA or AVP log with GENERIC's required fields is not parsed as a GENERIC log."""
    raw_data = {"engine": engine, "timestamp": TIMESTAMP, "decision": True}

    log = DetailedAuditLogModel.parse_obj(detailed_audit_log(raw_data))

    assert type(log.raw_data) is DummyEngineModel
    assert log.raw_data.engine == Engine(engine)
