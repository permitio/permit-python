"""Contract tests for api_coverage.py.

These pin what the workflows rely on: which operations count as covered, which
results fail the report and which are only listed, that the allowlist explains exactly
what it records and goes stale when it no longer does, and that a report that could not
run exits 2 and never reads as clean. The last tests run the report on the committed
snapshots and allowlist, with planted failures.

Run with:
uv run --only-dev pytest -c .github/scripts/pytest.ini .github/scripts/test_api_coverage.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parent / "api_coverage.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = REPO_ROOT / ".github" / "api-specs"
ALLOWLIST = Path(__file__).parent / "api_coverage_allowlist.json"

sys.path.insert(0, str(Path(__file__).parent))

import api_coverage  # noqa: E402 - importable only once sys.path has its directory
from api_coverage import (  # noqa: E402
    DEPRECATED,
    EAP,
    GA,
    load_spec,
    main,
    normalize,
    stage_of,
    template_pattern,
)

CONTROL_PLANE = api_coverage.CONTROL_PLANE

# A small control plane: a list route, a literal route beside a parameterized one, and a
# route with a trailing slash.
CP_OPS: list[tuple[str, str, dict[str, Any]]] = [
    ("GET", "/v2/users", {"tags": ["Users"]}),
    ("GET", "/v2/users/{user_id}", {"tags": ["Users"]}),
    ("GET", "/v2/groups/direct", {"tags": ["Groups"]}),
    ("GET", "/v2/groups/{group_key}", {"tags": ["Groups"], "deprecated": True}),
    ("GET", "/v2/templates/", {"tags": ["Email Templates"]}),
    ("POST", "/v2/requests", {"tags": ["Access Requests (EAP)"]}),
]
PDP_OPS: list[tuple[str, str, dict[str, Any]]] = [
    ("POST", "/allowed", {"tags": ["Authorization API"]}),
]
# A request for every GA operation above, so a report on them passes.
COVERING = [
    ("GET", "/v2/users"),
    ("GET", "/v2/users/u1"),
    ("GET", "/v2/groups/direct"),
    ("GET", "/v2/templates/"),
    ("POST", "/allowed"),
]


def spec_document(operations: list[tuple[str, str, dict[str, Any]]]) -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = {}
    for method, path, extra in operations:
        paths.setdefault(path, {})[method.lower()] = {"summary": f"{method} {path}", **extra}
    return {"openapi": "3.1.0", "info": {"title": "test"}, "paths": paths}


def request_line(
    method: str, path: str, *, status: int | None = 200, test: str = "t::a", e2e: bool = False
) -> dict[str, Any]:
    return {
        "kind": "request",
        "method": method,
        "path": path,
        "status": status,
        "test": test,
        "e2e": e2e,
    }


def write_record(
    path: Path,
    requests: list[dict[str, Any]],
    *,
    exitstatus: int = 0,
    header: bool = True,
    session: bool = True,
) -> Path:
    lines = [{"kind": "header", "version": 1}] if header else []
    lines += requests
    if session:
        lines.append({"kind": "session", "exitstatus": exitstatus, "tests": 3})
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


def entry(
    operation: str,
    *,
    api: str = CONTROL_PLANE,
    stage: str = GA,
    status: str = "excluded",
    ticket: str = "PER-1",
    reason: str = "a reason",
) -> dict[str, Any]:
    return {
        "api": api,
        "operation": operation,
        "stage": stage,
        "status": status,
        "ticket": ticket,
        "reason": reason,
    }


def sdk_only(request: str, *, status: str = "test-only", ticket: str = "") -> dict[str, Any]:
    return {"request": request, "status": status, "ticket": ticket, "reason": "a reason"}


@dataclass
class Outcome:
    code: int
    summary: str
    result: dict[str, Any]
    output: str


def report(
    tmp_path: Path,
    *,
    requests: list[tuple[str, str]] | list[dict[str, Any]] = COVERING,
    cp_ops: list[tuple[str, str, dict[str, Any]]] = CP_OPS,
    pdp_ops: list[tuple[str, str, dict[str, Any]]] = PDP_OPS,
    operations: list[dict[str, Any]] | None = None,
    sdk_only_entries: list[dict[str, Any]] | None = None,
    e2e: list[list[dict[str, Any]]] | None = None,
    extra: tuple[str, ...] = (),
) -> Outcome:
    """Write every input to tmp_path and run the report on them in-process."""
    (tmp_path / "cp.json").write_text(json.dumps(spec_document(cp_ops)), encoding="utf-8")
    (tmp_path / "pdp.json").write_text(json.dumps(spec_document(pdp_ops)), encoding="utf-8")
    lines = [r if isinstance(r, dict) else request_line(*r) for r in requests]
    write_record(tmp_path / "offline.jsonl", lines)
    allowlist = {"operations": operations or [], "sdk_only": sdk_only_entries or []}
    (tmp_path / "allowlist.json").write_text(json.dumps(allowlist), encoding="utf-8")
    e2e_args: list[str] = []
    for index, record in enumerate(e2e or []):
        e2e_args += ["--e2e-record", str(write_record(tmp_path / f"e2e-{index}.jsonl", record))]
    return run_report(
        tmp_path,
        "--spec",
        f"control-plane={tmp_path / 'cp.json'}",
        "--spec",
        f"pdp={tmp_path / 'pdp.json'}",
        "--allowlist",
        str(tmp_path / "allowlist.json"),
        "--record",
        str(tmp_path / "offline.jsonl"),
        "--min-records",
        "1",
        "--min-operations",
        "control-plane=1",
        "--min-operations",
        "pdp=1",
        *e2e_args,
        *extra,
    )


def run_report(tmp_path: Path, *args: str) -> Outcome:
    summary, result, output = tmp_path / "summary.md", tmp_path / "result.json", tmp_path / "out"
    for stale_output in (summary, result, output):
        stale_output.unlink(missing_ok=True)
    code = main(
        [
            "report",
            *args,
            "--summary",
            str(summary),
            "--json",
            str(result),
            "--github-output",
            str(output),
        ]
    )
    return Outcome(
        code=code,
        summary=summary.read_text(encoding="utf-8"),
        result=json.loads(result.read_text(encoding="utf-8")),
        output=output.read_text(encoding="utf-8") if output.exists() else "",
    )


def statuses(outcome: Outcome) -> dict[str, str]:
    return {op["operation"]: op["status"] for op in outcome.result["operations"]}


def problems(outcome: Outcome, kind: str) -> list[str]:
    return [p["subject"] for p in outcome.result["problems"] if p["kind"] == kind]


# --- passing and failing ------------------------------------------------------


def test_every_ga_operation_covered_passes(tmp_path: Path) -> None:
    outcome = report(tmp_path)
    assert outcome.code == 0, outcome.summary
    assert "Every GA operation is covered or allowlisted" in outcome.summary
    assert outcome.result["result"] == "pass"
    assert statuses(outcome)["GET /v2/users/{user_id}"] == "covered"
    assert outcome.output == "missing=0\nstale=0\nchanged=0\nsdk_only=0\n"


def test_a_ga_operation_no_test_sends_fails_and_is_named(tmp_path: Path) -> None:
    outcome = report(tmp_path, requests=[r for r in COVERING if r[1] != "/v2/users/u1"])
    assert outcome.code == 1
    assert problems(outcome, "missing") == ["Control plane GET /v2/users/{user_id}"]
    assert statuses(outcome)["GET /v2/users/{user_id}"] == "missing"
    assert "GA operations neither covered nor allowlisted" in outcome.summary
    assert "missing=1\n" in outcome.output


def test_missing_eap_and_deprecated_operations_are_listed_but_do_not_fail(tmp_path: Path) -> None:
    outcome = report(tmp_path)
    assert outcome.code == 0
    assert statuses(outcome)["POST /v2/requests"] == "missing"
    assert statuses(outcome)["GET /v2/groups/{group_key}"] == "missing"
    assert "Missing operations (2)" in outcome.summary


def test_a_missing_pdp_operation_fails_like_a_control_plane_one(tmp_path: Path) -> None:
    outcome = report(tmp_path, requests=[r for r in COVERING if r[1] != "/allowed"])
    assert outcome.code == 1
    assert problems(outcome, "missing") == ["PDP POST /allowed"]


def test_allowlisted_operations_do_not_fail(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        requests=[r for r in COVERING if r[1] != "/v2/users/u1"],
        operations=[entry("GET /v2/users/{user_id}", status="untested", reason="sdk.users.get()")],
    )
    assert outcome.code == 0, outcome.summary
    assert statuses(outcome)["GET /v2/users/{user_id}"] == "untested"
    assert "sdk.users.get()" in outcome.summary


def test_offline_requests_count_whatever_status_they_got(tmp_path: Path) -> None:
    requests = [request_line(method, path, status=None) for method, path in COVERING]
    assert report(tmp_path, requests=requests).code == 0


def test_requests_from_e2e_tests_in_the_offline_record_do_not_count(tmp_path: Path) -> None:
    requests = [request_line(m, p, e2e=p == "/v2/users/u1") for m, p in COVERING]
    outcome = report(tmp_path, requests=requests)
    assert outcome.code == 1
    assert problems(outcome, "missing") == ["Control plane GET /v2/users/{user_id}"]


# --- stages and matching ------------------------------------------------------


@pytest.mark.parametrize(
    ("operation", "stage"),
    [
        ({"tags": ["Users"]}, GA),
        ({"tags": ["Access Requests (EAP)"]}, EAP),
        ({"tags": ["OPAL Data ( EAP )"]}, EAP),
        ({"tags": ["Users"], "summary": "List group users (EAP)"}, GA),
        ({"tags": ["Groups"], "deprecated": True}, DEPRECATED),
        ({"tags": ["Policy Guards (EAP)"], "deprecated": True}, DEPRECATED),
        ({"tags": ["LEAP year"]}, GA),
        ({}, GA),
    ],
)
def test_stage_follows_the_deprecated_flag_then_the_tags(
    operation: dict[str, Any], stage: str
) -> None:
    assert stage_of(operation) == stage


def test_a_literal_segment_beats_a_parameter(tmp_path: Path) -> None:
    outcome = report(tmp_path)
    tests = {op["operation"]: op["test_count"] for op in outcome.result["operations"]}
    assert tests["GET /v2/groups/direct"] == 1
    assert tests["GET /v2/groups/{group_key}"] == 0


@pytest.mark.parametrize(
    ("template", "path", "matches"),
    [
        ("/v2/users/{user_id}", "/v2/users/u1", True),
        ("/v2/users/{user_id}", "/v2/users/a%2Fb", True),
        ("/v2/users/{user_id}", "/v2/users/a/b", False),
        ("/v2/users/{user_id}", "/v2/users/", False),
        ("/v2/users/{user_id}", "/v2/users/u1/roles", False),
        ("/v2/templates/", "/v2/templates", False),
        ("/v2/templates/", "/v2/templates/", True),
        ("/v2/users", "/v2/users.json", False),
        ("/v2/a.b", "/v2/aXb", False),
    ],
)
def test_template_pattern(template: str, path: str, *, matches: bool) -> None:
    assert bool(template_pattern(template).match(path)) is matches


def test_a_request_with_another_method_does_not_cover_the_operation(tmp_path: Path) -> None:
    requests = [*COVERING[:1], ("DELETE", "/v2/users/u1"), *COVERING[2:]]
    outcome = report(tmp_path, requests=requests)
    assert problems(outcome, "missing") == ["Control plane GET /v2/users/{user_id}"]
    assert problems(outcome, "sdk-only") == ["DELETE /v2/users/u1 (sent by t::a)"]


def test_parameter_names_do_not_decide_identity() -> None:
    assert normalize("/v2/{proj_id}/users/{user_id}") == normalize("/v2/{p}/users/{key}")


def test_an_entry_matches_an_operation_whose_parameters_were_renamed(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        requests=[r for r in COVERING if r[1] != "/v2/users/u1"],
        operations=[entry("GET /v2/users/{user_key}")],
    )
    assert outcome.code == 0, outcome.summary


# --- allowlist staleness and changes ------------------------------------------


def test_an_entry_for_an_operation_a_test_now_covers_is_stale(tmp_path: Path) -> None:
    outcome = report(tmp_path, operations=[entry("GET /v2/users/{user_id}", status="deferred")])
    assert outcome.code == 1
    assert problems(outcome, "stale") == ["Control plane GET /v2/users/{user_id}"]
    assert statuses(outcome)["GET /v2/users/{user_id}"] == "covered"
    assert "Stale allowlist entries" in outcome.summary


def test_an_entry_for_an_operation_not_in_the_spec_is_stale(tmp_path: Path) -> None:
    outcome = report(tmp_path, operations=[entry("GET /v2/gone")])
    assert outcome.code == 1
    assert problems(outcome, "stale") == ["Control plane GET /v2/gone"]


def test_an_entry_for_the_other_api_is_stale(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        requests=[r for r in COVERING if r[1] != "/allowed"],
        operations=[entry("POST /allowed", api=CONTROL_PLANE)],
    )
    assert problems(outcome, "stale") == ["Control plane POST /allowed"]
    assert problems(outcome, "missing") == ["PDP POST /allowed"]


def test_an_entry_whose_stage_changed_fails(tmp_path: Path) -> None:
    outcome = report(tmp_path, operations=[entry("POST /v2/requests", stage=GA)])
    assert outcome.code == 1
    assert problems(outcome, "changed") == ["Control plane POST /v2/requests"]
    detail = next(p["detail"] for p in outcome.result["problems"] if p["kind"] == "changed")
    assert detail == "allowlisted as GA, now EAP in the spec"


def test_an_eap_operation_that_turns_ga_fails_even_though_it_is_allowlisted(
    tmp_path: Path,
) -> None:
    cp_ops = [*CP_OPS[:-1], ("POST", "/v2/requests", {"tags": ["Access Requests"]})]
    outcome = report(tmp_path, cp_ops=cp_ops, operations=[entry("POST /v2/requests", stage=EAP)])
    assert outcome.code == 1
    assert problems(outcome, "changed") == ["Control plane POST /v2/requests"]


# --- SDK-only requests --------------------------------------------------------


def test_a_request_no_spec_operation_matches_fails(tmp_path: Path) -> None:
    outcome = report(tmp_path, requests=[*COVERING, ("POST", "/v2/echo")])
    assert outcome.code == 1
    assert problems(outcome, "sdk-only") == ["POST /v2/echo (sent by t::a)"]
    assert "**not allowlisted**" in outcome.summary


def test_an_sdk_only_entry_explains_matching_requests(tmp_path: Path) -> None:
    requests = [*COVERING, ("DELETE", "/facts/tenants/t1"), ("DELETE", "/facts/tenants/t2")]
    outcome = report(
        tmp_path,
        requests=requests,
        sdk_only_entries=[
            sdk_only("DELETE /facts/tenants/{tenant_id}", status="undocumented", ticket="PER-2")
        ],
    )
    assert outcome.code == 0, outcome.summary
    assert outcome.result["sdk_only"][0]["request"] == "DELETE /facts/tenants/{tenant_id}"
    assert outcome.result["sdk_only"][0]["requests"] == 2


def test_an_sdk_only_entry_no_request_matches_is_stale(tmp_path: Path) -> None:
    outcome = report(tmp_path, sdk_only_entries=[sdk_only("POST /v2/echo")])
    assert outcome.code == 1
    assert problems(outcome, "stale") == ["POST /v2/echo"]


def test_an_sdk_only_entry_for_a_route_the_spec_now_lists_goes_stale(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        requests=[*COVERING, ("POST", "/v2/echo")],
        cp_ops=[*CP_OPS, ("POST", "/v2/echo", {"tags": ["Echo"]})],
        sdk_only_entries=[sdk_only("POST /v2/echo")],
    )
    assert outcome.code == 1
    assert problems(outcome, "stale") == ["POST /v2/echo"]
    assert statuses(outcome)["POST /v2/echo"] == "covered"


# --- the end-to-end column ----------------------------------------------------


def test_without_an_e2e_record_the_column_says_not_run(tmp_path: Path) -> None:
    outcome = report(tmp_path, operations=[entry("POST /v2/requests", stage=EAP)])
    assert "End to end: **not run** (no end-to-end record was given)" in outcome.summary
    assert outcome.result["e2e"] == "not run"
    assert {op["e2e"] for op in outcome.result["operations"]} == {"not run"}
    assert "| Control plane | GA | 4 | 4 | 0 | 0 | 0 | 0 | not run |" in outcome.summary
    covered = "| Control plane | `GET /v2/users/{user_id}` | GA | 1 | not run |"
    missing = "| `GET /v2/groups/{group_key}` | deprecated | GET /v2/groups/{group_key} | not run |"
    allowlisted = "| Control plane | `POST /v2/requests` | EAP | PER-1 | a reason | not run |"
    for row in (covered, missing, allowlisted):
        assert row in outcome.summary


def test_an_e2e_record_without_e2e_requests_also_says_not_run(tmp_path: Path) -> None:
    outcome = report(tmp_path, e2e=[[request_line("GET", "/v2/users", e2e=False)]])
    assert "the end-to-end records hold no e2e request" in outcome.summary
    assert {op["e2e"] for op in outcome.result["operations"]} == {"not run"}


def test_e2e_requests_fill_the_column_only_on_success(tmp_path: Path) -> None:
    e2e = [
        request_line("GET", "/v2/users", status=200, e2e=True),
        request_line("GET", "/v2/users/u1", status=404, e2e=True),
        request_line("POST", "/allowed", status=None, e2e=True),
        request_line("GET", "/v2/groups/direct", status=200, e2e=False),
    ]
    outcome = report(tmp_path, e2e=[e2e])
    exercised = {op["operation"]: op["e2e"] for op in outcome.result["operations"]}
    assert exercised["GET /v2/users"] is True
    assert exercised["GET /v2/users/{user_id}"] is False
    assert exercised["POST /allowed"] is False
    assert exercised["GET /v2/groups/direct"] is False
    assert "| Control plane | GA | 4 | 4 | 0 | 0 | 0 | 0 | 1 |" in outcome.summary


def test_e2e_requests_never_make_an_operation_covered(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        requests=[r for r in COVERING if r[1] != "/v2/users/u1"],
        e2e=[[request_line("GET", "/v2/users/u1", e2e=True)]],
    )
    assert outcome.code == 1
    assert problems(outcome, "missing") == ["Control plane GET /v2/users/{user_id}"]
    assert "| Control plane | `GET /v2/users/{user_id}` | GA | GET /v2/users/{user_id} | yes |" in (
        outcome.summary
    )


def test_an_allowlisted_operation_shows_whether_e2e_tests_exercised_it(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        requests=[r for r in COVERING if r[1] != "/v2/users/u1"],
        operations=[entry("GET /v2/users/{user_id}", status="untested", reason="users.get()")],
        e2e=[[request_line("GET", "/v2/users/u1", e2e=True)]],
    )
    assert outcome.code == 0, outcome.summary
    assert "| `GET /v2/users/{user_id}` | GA | PER-1 | users.get() | yes |" in outcome.summary


def test_records_from_several_e2e_runs_add_up(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        e2e=[
            [request_line("GET", "/v2/users", e2e=True)],
            [request_line("POST", "/allowed", e2e=True)],
        ],
    )
    exercised = {op["operation"] for op in outcome.result["operations"] if op["e2e"] is True}
    assert exercised == {"GET /v2/users", "POST /allowed"}


def test_an_e2e_record_from_a_failed_session_is_used_and_flagged(tmp_path: Path) -> None:
    record = write_record(
        tmp_path / "failed.jsonl", [request_line("GET", "/v2/users", e2e=True)], exitstatus=1
    )
    outcome = report(tmp_path, extra=("--e2e-record", str(record)))
    assert outcome.code == 0
    assert "The session exited 1, so the column may be incomplete." in outcome.summary
    exercised = {op["operation"] for op in outcome.result["operations"] if op["e2e"] is True}
    assert exercised == {"GET /v2/users"}


def test_e2e_requests_that_match_nothing_are_listed(tmp_path: Path) -> None:
    outcome = report(tmp_path, e2e=[[request_line("GET", "/nowhere", e2e=True)]])
    assert outcome.code == 0
    assert outcome.result["e2e_unmatched"] == ["GET /nowhere"]


# --- did not run --------------------------------------------------------------


def assert_did_not_run(outcome: Outcome, message: str) -> None:
    assert outcome.code == 2
    assert "The report did not run" in outcome.summary
    assert "Every GA operation" not in outcome.summary
    assert outcome.result == {
        "result": "did-not-run",
        "exit_code": 2,
        "reason": outcome.result["reason"],
    }
    assert re.search(message, outcome.result["reason"]), outcome.result["reason"]


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ("", "is empty; the recorder never ran"),
        ("not json\n", "line 1 of the request record .* is not JSON"),
        ('{"kind": "header", "version": 2}\n', "does not start with a version 1 header"),
        ('{"kind": "request"}\n', "does not start with a version 1 header"),
        ('{"kind": "header", "version": 1}\n', "has no session line"),
        (
            '{"kind": "header", "version": 1}\n{"kind": "other"}\n',
            "line 2 of the request record .* has an unknown kind",
        ),
        (
            '{"kind": "header", "version": 1}\n{"kind": "request", "method": "GET"}\n',
            "line 2 .* is not a well-formed request",
        ),
        (
            (
                '{"kind": "header", "version": 1}\n'
                '{"kind": "session", "exitstatus": 0, "tests": 1}\n'
                '{"kind": "session", "exitstatus": 0, "tests": 1}\n'
            ),
            "continues after its session line",
        ),
        (
            '{"kind": "header", "version": 1}\n{"kind": "session", "exitstatus": "0"}\n',
            "session line .* is malformed",
        ),
        (
            '{"kind": "header", "version": 1}\n{"kind": "session", "exitstatus": 0, "tests": 1}\n',
            "holds 0 offline requests, fewer than the minimum of 1",
        ),
    ],
)
def test_a_record_that_cannot_be_trusted_exits_2(tmp_path: Path, record: str, message: str) -> None:
    report(tmp_path)
    (tmp_path / "offline.jsonl").write_text(record, encoding="utf-8")
    outcome = rerun(tmp_path)
    assert_did_not_run(outcome, message)


def rerun(
    tmp_path: Path,
    *extra: str,
    record: str = "offline.jsonl",
    min_operations: tuple[str, ...] = ("control-plane=1", "pdp=1"),
) -> Outcome:
    """Run the report again on the inputs report() wrote, with some of them replaced."""
    minimums = [arg for minimum in min_operations for arg in ("--min-operations", minimum)]
    return run_report(
        tmp_path,
        "--spec",
        f"control-plane={tmp_path / 'cp.json'}",
        "--spec",
        f"pdp={tmp_path / 'pdp.json'}",
        "--allowlist",
        str(tmp_path / "allowlist.json"),
        "--record",
        str(tmp_path / record),
        "--min-records",
        "1",
        *minimums,
        *extra,
    )


def test_a_missing_record_exits_2(tmp_path: Path) -> None:
    report(tmp_path)
    assert_did_not_run(rerun(tmp_path, record="absent.jsonl"), "could not read the request record")


def test_a_record_from_a_failed_offline_session_exits_2(tmp_path: Path) -> None:
    report(tmp_path)
    write_record(tmp_path / "failed.jsonl", [request_line("GET", "/v2/users")], exitstatus=1)
    assert_did_not_run(rerun(tmp_path, record="failed.jsonl"), "exited 1")


def test_fewer_offline_requests_than_the_minimum_exits_2(tmp_path: Path) -> None:
    report(tmp_path)
    assert_did_not_run(
        rerun(tmp_path, "--min-records", "6"),
        "holds 5 offline requests, fewer than the minimum of 6",
    )


def test_exactly_the_minimum_of_requests_and_operations_runs(tmp_path: Path) -> None:
    report(tmp_path)
    outcome = rerun(
        tmp_path,
        "--min-records",
        str(len(COVERING)),
        min_operations=(f"control-plane={len(CP_OPS)}", f"pdp={len(PDP_OPS)}"),
    )
    assert outcome.code == 0, outcome.summary


def test_one_operation_below_the_minimum_exits_2(tmp_path: Path) -> None:
    report(tmp_path)
    outcome = rerun(tmp_path, min_operations=("control-plane=1", f"pdp={len(PDP_OPS) + 1}"))
    assert_did_not_run(outcome, "PDP spec at .* lists 1 operations, fewer than the minimum of 2")


def test_e2e_requests_do_not_count_towards_the_offline_minimum(tmp_path: Path) -> None:
    report(tmp_path)
    requests = [request_line(m, p) for m, p in COVERING] + [
        request_line("GET", "/v2/users", e2e=True)
    ]
    write_record(tmp_path / "mixed.jsonl", requests)
    outcome = rerun(tmp_path, "--min-records", "6", record="mixed.jsonl")
    assert_did_not_run(outcome, "holds 5 offline requests")


def test_an_unreadable_e2e_record_exits_2(tmp_path: Path) -> None:
    report(tmp_path)
    (tmp_path / "e2e.jsonl").write_text("{}\n", encoding="utf-8")
    assert_did_not_run(
        rerun(tmp_path, "--e2e-record", str(tmp_path / "e2e.jsonl")),
        "does not start with a version 1",
    )


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (None, "could not read the Control plane spec"),
        ("<html>502</html>", "Control plane spec at .* is not valid JSON"),
        ("[]", "has no `paths` object"),
        ('{"paths": {}}', "lists 0 operations, fewer than the minimum of 1"),
        (
            '{"paths": {"/a/{x}": {"get": {}}, "/a/{y}": {"get": {}}}}',
            "GET /a/{y} and GET /a/{x} are the same operation",
        ),
    ],
)
def test_a_spec_that_cannot_be_read_exits_2(tmp_path: Path, spec: str | None, message: str) -> None:
    report(tmp_path)
    if spec is None:
        (tmp_path / "cp.json").unlink()
    else:
        (tmp_path / "cp.json").write_text(spec, encoding="utf-8")
    assert_did_not_run(rerun(tmp_path), message)


@pytest.mark.parametrize(
    ("sidecar", "message"),
    [
        ("not json", "the snapshot's source file at .* is not valid JSON"),
        ('{"source": "https://example.test"}', 'needs a "source" and a "fetched" string'),
        ('{"source": "", "fetched": "2026-01-02"}', 'needs a "source" and a "fetched" string'),
    ],
)
def test_a_snapshot_whose_source_file_is_broken_exits_2(
    tmp_path: Path, sidecar: str, message: str
) -> None:
    report(tmp_path)
    (tmp_path / "pdp.source.json").write_text(sidecar, encoding="utf-8")
    assert_did_not_run(rerun(tmp_path), message)


def test_a_snapshot_names_its_source_in_the_report(tmp_path: Path) -> None:
    (tmp_path / "pdp.source.json").write_text(
        '{"source": "a PDP | image", "fetched": "2026-01-02"}', encoding="utf-8"
    )
    outcome = report(tmp_path)
    assert "pdp.json`, a snapshot of a PDP \\| image taken 2026-01-02." in outcome.summary
    assert outcome.result["specs"]["pdp"].endswith("a snapshot of a PDP \\| image taken 2026-01-02")


def test_a_spec_with_fewer_operations_than_the_default_minimum_exits_2(tmp_path: Path) -> None:
    report(tmp_path)
    outcome = run_report(
        tmp_path,
        "--spec",
        f"control-plane={tmp_path / 'cp.json'}",
        "--spec",
        f"pdp={tmp_path / 'pdp.json'}",
        "--allowlist",
        str(tmp_path / "allowlist.json"),
        "--record",
        str(tmp_path / "offline.jsonl"),
        "--min-records",
        "1",
    )
    assert_did_not_run(outcome, "lists 6 operations, fewer than the minimum of 200")


@pytest.mark.parametrize(
    ("allowlist", "message"),
    [
        ("not json", "the allowlist at .* is not valid JSON"),
        ("[]", "is not a JSON object"),
        ('{"operations": []}', 'needs a "sdk_only" list of objects'),
        ('{"operations": [1], "sdk_only": []}', 'needs a "operations" list of objects'),
        (json.dumps({"operations": [entry("GET /v2/x", reason=" ")], "sdk_only": []}), '"reason"'),
        (
            json.dumps({"operations": [entry("GET /v2/x", status="ignored")], "sdk_only": []}),
            '"status" must be one of',
        ),
        (
            json.dumps({"operations": [entry("GET /v2/x", stage="beta")], "sdk_only": []}),
            '"stage" must be one of',
        ),
        (
            json.dumps({"operations": [entry("GET /v2/x", api="cloud")], "sdk_only": []}),
            '"api" must be one of',
        ),
        (
            json.dumps({"operations": [entry("get /v2/x")], "sdk_only": []}),
            "upper-case HTTP method",
        ),
        (json.dumps({"operations": [entry("GET v2/x")], "sdk_only": []}), "does not name a path"),
        (
            json.dumps(
                {"operations": [entry("GET /v2/x", status="deferred", ticket="")], "sdk_only": []}
            ),
            '"ticket"',
        ),
        (
            json.dumps({"operations": [entry("GET /v2/x", ticket="soon")], "sdk_only": []}),
            "not a ticket id",
        ),
        (
            json.dumps(
                {"operations": [entry("GET /v2/x/{a}"), entry("GET /v2/x/{b}")], "sdk_only": []}
            ),
            "listed more than once",
        ),
        (
            json.dumps({"operations": [], "sdk_only": [sdk_only("POST /v2/echo", status="odd")]}),
            '"status" must be',
        ),
        (
            json.dumps(
                {"operations": [], "sdk_only": [sdk_only("POST /v2/a", status="undocumented")]}
            ),
            '"ticket"',
        ),
        (
            json.dumps(
                {"operations": [], "sdk_only": [sdk_only("POST /v2/a"), sdk_only("POST /v2/a")]}
            ),
            "listed more than once",
        ),
    ],
)
def test_an_invalid_allowlist_exits_2(tmp_path: Path, allowlist: str, message: str) -> None:
    report(tmp_path)
    (tmp_path / "allowlist.json").write_text(allowlist, encoding="utf-8")
    assert_did_not_run(rerun(tmp_path), message)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--spec", "control-plane=a.json"), "--spec is needed for each of control-plane, pdp"),
        (("--spec", "cloud=a.json", "--spec", "pdp=b.json"), "NAME one of control-plane, pdp"),
        (("--spec", "pdp=a.json", "--spec", "pdp=b.json"), "--spec pdp is given more than once"),
    ],
)
def test_bad_spec_options_exit_2(tmp_path: Path, args: tuple[str, ...], message: str) -> None:
    report(tmp_path)
    outcome = run_report(
        tmp_path,
        *args,
        "--allowlist",
        str(tmp_path / "allowlist.json"),
        "--record",
        str(tmp_path / "x"),
    )
    assert_did_not_run(outcome, message)


def test_an_unexpected_error_exits_2_not_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(**_: object) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    report(tmp_path)
    monkeypatch.setattr(api_coverage, "build_report", explode)
    assert_did_not_run(rerun(tmp_path), "RuntimeError: boom")


def test_an_error_while_writing_the_outputs_exits_2(tmp_path: Path) -> None:
    report(tmp_path)
    code = main(
        [
            "report",
            "--spec",
            f"control-plane={tmp_path / 'cp.json'}",
            "--spec",
            f"pdp={tmp_path / 'pdp.json'}",
            "--allowlist",
            str(tmp_path / "allowlist.json"),
            "--record",
            str(tmp_path / "offline.jsonl"),
            "--min-records",
            "1",
            "--min-operations",
            "control-plane=1",
            "--min-operations",
            "pdp=1",
            "--summary",
            str(tmp_path),
        ]
    )
    assert code == 2


# --- outputs ------------------------------------------------------------------


def test_github_output_carries_one_count_per_failure_kind(tmp_path: Path) -> None:
    outcome = report(
        tmp_path,
        requests=[*COVERING[1:], ("POST", "/v2/echo")],
        operations=[entry("GET /v2/gone"), entry("POST /v2/requests")],
    )
    assert outcome.output == "missing=1\nstale=1\nchanged=1\nsdk_only=1\n"


def test_the_summary_is_appended_to_the_given_file(tmp_path: Path) -> None:
    report(tmp_path)
    summary = tmp_path / "step-summary.md"
    summary.write_text("earlier step\n", encoding="utf-8")
    code = main(
        [
            "report",
            "--spec",
            f"control-plane={tmp_path / 'cp.json'}",
            "--spec",
            f"pdp={tmp_path / 'pdp.json'}",
            "--allowlist",
            str(tmp_path / "allowlist.json"),
            "--record",
            str(tmp_path / "offline.jsonl"),
            "--min-records",
            "1",
            "--min-operations",
            "control-plane=1",
            "--min-operations",
            "pdp=1",
            "--summary",
            str(summary),
        ]
    )
    assert code == 0
    assert summary.read_text(encoding="utf-8").startswith("earlier step\n## API coverage\n")


def test_pipes_and_backticks_cannot_break_the_tables(tmp_path: Path) -> None:
    cp_ops = [*CP_OPS, ("GET", "/v2/odd", {"tags": ["Odd"], "summary": "a | b `c`"})]
    outcome = report(tmp_path, cp_ops=cp_ops, operations=[entry("GET /v2/odd", reason="x | `y`")])
    assert "x \\| 'y'" in outcome.summary
    assert "x | `y`" not in outcome.summary


def test_the_json_result_lists_every_operation_with_its_tests(tmp_path: Path) -> None:
    requests = [request_line(m, p, test=f"t::{i}") for i, (m, p) in enumerate(COVERING)]
    requests += [request_line("GET", "/v2/users", test=f"t::more{i}") for i in range(6)]
    outcome = report(tmp_path, requests=requests)
    users = next(op for op in outcome.result["operations"] if op["operation"] == "GET /v2/users")
    assert users["test_count"] == 7
    assert len(users["tests"]) == 5
    assert users["stage"] == GA
    assert users["tags"] == ["Users"]
    assert len(outcome.result["operations"]) == len(CP_OPS) + len(PDP_OPS)
    assert outcome.result["offline"] == {"requests": 11, "tests": 3}


def test_a_baseline_lists_the_spec_changes_since_the_snapshot(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    old = [
        *CP_OPS[:-1],
        ("POST", "/v2/requests", {"tags": ["Access Requests"]}),
        ("GET", "/v2/old", {}),
    ]
    baseline.write_text(json.dumps(spec_document(old)), encoding="utf-8")
    outcome = report(tmp_path, extra=("--baseline", f"control-plane={baseline}"))
    assert outcome.result["baselines"] == [
        {
            "api": CONTROL_PLANE,
            "added": [],
            "removed": ["GET /v2/old"],
            "restaged": [{"operation": "POST /v2/requests", "was": GA, "now": EAP}],
        }
    ]
    assert "- removed: `GET /v2/old` (GA)" in outcome.summary


# --- snapshots ----------------------------------------------------------------


def test_a_snapshot_keeps_what_the_report_reads_and_records_its_source(tmp_path: Path) -> None:
    document = spec_document(CP_OPS)
    document["components"] = {"schemas": {"Big": {"type": "object"}}}
    document["paths"]["/v2/users"]["get"]["responses"] = {"200": {"description": "ok"}}
    document["paths"]["/v2/users"]["parameters"] = [{"name": "x"}]
    source = tmp_path / "full.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    code = main(
        [
            "snapshot",
            "control-plane",
            str(source),
            "--source",
            "https://example.test/openapi.json",
            "--fetched",
            "2026-01-02",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == 0
    snapshot = json.loads((tmp_path / "out" / "control-plane.json").read_text(encoding="utf-8"))
    assert "components" not in snapshot
    assert snapshot["paths"]["/v2/users"] == {
        "get": {"operationId": None, "summary": "GET /v2/users", "tags": ["Users"]}
    }
    assert snapshot["paths"]["/v2/groups/{group_key}"]["get"]["deprecated"] is True
    sidecar = json.loads(
        (tmp_path / "out" / "control-plane.source.json").read_text(encoding="utf-8")
    )
    assert sidecar == {
        "source": "https://example.test/openapi.json",
        "fetched": "2026-01-02",
        "operations": len(CP_OPS),
    }
    full = load_spec(CONTROL_PLANE, source, 1)
    reduced = load_spec(CONTROL_PLANE, tmp_path / "out" / "control-plane.json", 1)
    assert sorted((o.name, o.stage, o.tags) for o in reduced.operations) == sorted(
        (o.name, o.stage, o.tags) for o in full.operations
    )
    assert "a snapshot of https://example.test/openapi.json taken 2026-01-02" in reduced.source


def test_a_snapshot_of_a_document_without_operations_fails(tmp_path: Path) -> None:
    source = tmp_path / "empty.json"
    source.write_text('{"paths": {}}', encoding="utf-8")
    code = main(["snapshot", "pdp", str(source), "--source", "x", "--out-dir", str(tmp_path)])
    assert code == 2
    assert not (tmp_path / "pdp.json").exists()


@pytest.mark.parametrize("api", ["control-plane", "pdp"])
def test_the_committed_snapshots_are_their_own_inventory(tmp_path: Path, api: str) -> None:
    committed = SNAPSHOTS / f"{api}.json"
    sidecar = json.loads((SNAPSHOTS / f"{api}.source.json").read_text(encoding="utf-8"))
    code = main(
        [
            "snapshot",
            api,
            str(committed),
            "--source",
            sidecar["source"],
            "--fetched",
            sidecar["fetched"],
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert (tmp_path / f"{api}.json").read_text(encoding="utf-8") == committed.read_text(
        encoding="utf-8"
    )
    assert json.loads((tmp_path / f"{api}.source.json").read_text(encoding="utf-8")) == sidecar


TEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"
PINNED_PDP_IMAGE = re.compile(r"^\s*PINNED_PDP_IMAGE:\s*(?:>-\s*\n\s*)?(\S+)\s*$", re.MULTILINE)
SNAPSHOT_IMAGE = re.compile(r"^GET /openapi\.json on a container of (\S+) ")


def test_the_pdp_snapshot_comes_from_the_pinned_pdp_image() -> None:
    """Moving PINNED_PDP_IMAGE without refreshing the PDP snapshot fails here."""
    pins = PINNED_PDP_IMAGE.findall(TEST_WORKFLOW.read_text(encoding="utf-8"))
    assert len(pins) == 1, f"expected one PINNED_PDP_IMAGE in {TEST_WORKFLOW}, found {pins}"
    source = json.loads((SNAPSHOTS / "pdp.source.json").read_text(encoding="utf-8"))["source"]
    taken_from = SNAPSHOT_IMAGE.match(source)
    assert taken_from is not None, f"pdp.source.json names no PDP image: {source}"
    assert taken_from.group(1) == pins[0], (
        f"pdp.json was taken from {taken_from.group(1)}, but test.yml pins {pins[0]}: "
        "refresh it (CONTRIBUTING.md, 'API coverage report')"
    )


# --- the committed snapshots and allowlist, with planted failures -------------


def concrete(template: str) -> str:
    return re.sub(r"\{[^/{}]*\}", "x", template)


def complete_record(allowlist: dict[str, Any]) -> list[dict[str, Any]]:
    """A request for every committed operation the allowlist leaves out, and per sdk_only entry."""
    listed = {(e["api"], normalize(e["operation"])) for e in allowlist["operations"]}
    requests = [
        request_line(operation.method, concrete(operation.path))
        for api in ("control-plane", "pdp")
        for operation in load_spec(api, SNAPSHOTS / f"{api}.json", 1).operations
        if (api, normalize(operation.name)) not in listed
    ]
    method_paths = [e["request"].split(" ", 1) for e in allowlist["sdk_only"]]
    requests += [request_line(method, concrete(path)) for method, path in method_paths]
    return requests


def committed_report(
    tmp_path: Path,
    *,
    requests: list[dict[str, Any]] | None = None,
    allowlist: dict[str, Any] | None = None,
    control_plane: dict[str, Any] | None = None,
) -> Outcome:
    allowlist = allowlist or json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text(json.dumps(allowlist), encoding="utf-8")
    cp_path = SNAPSHOTS / "control-plane.json"
    if control_plane is not None:
        cp_path = tmp_path / "control-plane.json"
        cp_path.write_text(json.dumps(control_plane), encoding="utf-8")
    record = write_record(
        tmp_path / "offline.jsonl", complete_record(allowlist) if requests is None else requests
    )
    return run_report(
        tmp_path,
        "--spec",
        f"control-plane={cp_path}",
        "--spec",
        f"pdp={SNAPSHOTS / 'pdp.json'}",
        "--allowlist",
        str(allowlist_path),
        "--record",
        str(record),
        "--min-records",
        "1",
    )


def test_the_committed_allowlist_agrees_with_the_committed_snapshots(tmp_path: Path) -> None:
    """Every entry names an operation in the snapshot, at the stage the snapshot gives it."""
    outcome = committed_report(tmp_path)
    assert outcome.code == 0, outcome.summary
    allowlist = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    assert all(e["reason"].strip() for e in allowlist["operations"] + allowlist["sdk_only"])


def test_planted_a_new_ga_operation_in_the_snapshot_fails(tmp_path: Path) -> None:
    snapshot = json.loads((SNAPSHOTS / "control-plane.json").read_text(encoding="utf-8"))
    snapshot["paths"]["/v2/planted/{planted_id}"] = {
        "get": {"summary": "Planted", "tags": ["Planted"]}
    }
    allowlist = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    outcome = committed_report(
        tmp_path, requests=complete_record(allowlist), control_plane=snapshot
    )
    assert outcome.code == 1
    assert problems(outcome, "missing") == ["Control plane GET /v2/planted/{planted_id}"]


def test_planted_a_new_eap_operation_in_the_snapshot_is_listed_but_passes(tmp_path: Path) -> None:
    snapshot = json.loads((SNAPSHOTS / "control-plane.json").read_text(encoding="utf-8"))
    snapshot["paths"]["/v2/planted"] = {"get": {"summary": "Planted", "tags": ["Planted (EAP)"]}}
    allowlist = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    outcome = committed_report(
        tmp_path, requests=complete_record(allowlist), control_plane=snapshot
    )
    assert outcome.code == 0, outcome.summary
    assert statuses(outcome)["GET /v2/planted"] == "missing"


def test_planted_a_stale_allowlist_entry_fails(tmp_path: Path) -> None:
    allowlist = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    requests = complete_record(allowlist)
    allowlist["operations"].append(entry("GET /v2/api-key/scope", status="excluded"))
    outcome = committed_report(tmp_path, requests=requests, allowlist=allowlist)
    assert outcome.code == 1
    assert problems(outcome, "stale") == ["Control plane GET /v2/api-key/scope"]


def test_planted_an_empty_record_does_not_run(tmp_path: Path) -> None:
    assert_did_not_run(committed_report(tmp_path, requests=[]), "holds 0 offline requests")


def test_the_report_runs_as_a_script(tmp_path: Path) -> None:
    report(tmp_path)
    completed = subprocess.run(  # noqa: S603 - runs the script under test with this interpreter
        [
            sys.executable,
            str(SCRIPT),
            "report",
            "--spec",
            f"control-plane={tmp_path / 'cp.json'}",
            "--spec",
            f"pdp={tmp_path / 'pdp.json'}",
            "--allowlist",
            str(tmp_path / "allowlist.json"),
            "--record",
            str(tmp_path / "offline.jsonl"),
            "--min-records",
            "1",
            "--min-operations",
            "control-plane=1",
            "--min-operations",
            "pdp=1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("## API coverage")


def test_bad_arguments_exit_2(tmp_path: Path) -> None:
    completed = subprocess.run(  # noqa: S603 - runs the script under test with this interpreter
        [sys.executable, str(SCRIPT), "report", "--record", str(tmp_path / "x")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "the following arguments are required: --allowlist" in completed.stderr
