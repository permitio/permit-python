"""Contract tests for format_audit.py.

These lock the parts the workflow silently depends on: the marker is always the
first line, bad input still exits 0, untrusted advisory text cannot break out
of a fence or a workflow command, and a pip-audit that did not check a tree is
always named rather than passing for a clean result.

Run with: python -m pytest .github/scripts/test_format_audit.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "format_audit.py"

sys.path.insert(0, str(Path(__file__).parent))

from format_audit import (  # noqa: E402
    MARKER,
    Finding,
    merge,
    parse_pip_audit,
    parse_trivy,
    render,
    render_annotations,
    render_slack,
    trivy_scanned_nothing,
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def trivy_report(*vulns: dict) -> dict:
    return {
        "SchemaVersion": 2,
        "Results": [{"Target": "requirements.txt", "Type": "pip", "Vulnerabilities": list(vulns)}],
    }


def clean_report() -> dict:
    """What Trivy really writes for a scanned file with no advisories.

    Verified against actual output: a clean scan still carries a Target and a
    populated Packages list. `Results: null` means Trivy recognised nothing to
    scan, which is a different thing entirely -- see test_gate_fails_closed_
    when_trivy_scanned_nothing.
    """
    return {
        "SchemaVersion": 2,
        "Results": [
            {
                "Target": "requirements.txt",
                "Class": "lang-pkgs",
                "Type": "pip",
                "Packages": [{"Name": "aiohttp", "Version": "3.14.3"}],
            }
        ],
    }


def vuln(**kwargs) -> dict:
    base = {
        "VulnerabilityID": "CVE-2026-69244",
        "PkgName": "aiohttp",
        "InstalledVersion": "3.12.14",
        "FixedVersion": "3.14.3",
        "Severity": "HIGH",
        "Title": "Out-of-bounds read in the HTTP response parser",
        "PrimaryURL": "https://avd.aquasec.com/nvd/cve-2026-69244",
    }
    base.update(kwargs)
    return base


# --- CLI contract -----------------------------------------------------------


def test_missing_argument_exits_2():
    result = run()
    assert result.returncode == 2


def test_garbage_input_still_exits_0_with_marker(tmp_path: Path):
    bad = tmp_path / "trivy.json"
    bad.write_bytes(b"\x00\x01not json at all{{{")
    result = run(str(bad))
    assert result.returncode == 0, "a non-zero exit would drop the PR comment entirely"
    assert result.stdout.split("\n")[0] == MARKER
    assert "could not be parsed" in result.stdout or "not valid JSON" in result.stdout
    assert "No known vulnerabilities found" not in result.stdout


def test_empty_file_exits_0_and_does_not_claim_clean(tmp_path: Path):
    empty = tmp_path / "trivy.json"
    empty.write_text("")
    result = run(str(empty))
    assert result.returncode == 0
    assert result.stdout.split("\n")[0] == MARKER
    assert "No known vulnerabilities found" not in result.stdout


def test_missing_file_exits_0(tmp_path: Path):
    result = run(str(tmp_path / "nope.json"))
    assert result.returncode == 0
    assert result.stdout.split("\n")[0] == MARKER


def test_clean_report_reports_clean(tmp_path: Path):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps(clean_report()))
    result = run(str(report))
    assert result.returncode == 0
    assert result.stdout.split("\n")[0] == MARKER
    assert "No known vulnerabilities found" in result.stdout


def test_vulnerable_report_lists_the_finding(tmp_path: Path):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps(trivy_report(vuln())))
    result = run(str(report))
    assert result.returncode == 0
    assert result.stdout.split("\n")[0] == MARKER
    assert "CVE-2026-69244" in result.stdout
    assert "aiohttp" in result.stdout
    assert "3.14.3" in result.stdout
    assert "No known vulnerabilities found" not in result.stdout


# --- marker is present in every state ---------------------------------------


@pytest.mark.parametrize(
    "findings,errors",
    [
        ([], []),
        ([], ["trivy: boom"]),
        ([Finding("CVE-1", "pkg", "1.0", "HIGH", "2.0", "t", "", "trivy")], []),
        ([Finding("CVE-1", "pkg", "1.0", "LOW", "2.0", "t", "", "trivy")], ["trivy: boom"]),
    ],
)
def test_marker_is_first_line_in_every_state(findings, errors):
    out = render(findings, errors, "", blocking=True)
    assert out.split("\n")[0] == MARKER


# --- parsing ----------------------------------------------------------------


def test_labelled_trivy_reports_are_tagged_with_their_tree(tmp_path: Path):
    ceiling = tmp_path / "ceiling.json"
    floor = tmp_path / "floor.json"
    ceiling.write_text(json.dumps(clean_report()))
    floor.write_text(json.dumps(trivy_report(vuln())))
    result = run(f"ceiling={ceiling}", f"floor={floor}")
    assert result.returncode == 0
    assert result.stdout.split("\n")[0] == MARKER
    assert "trivy:floor" in result.stdout
    assert "CVE-2026-69244" in result.stdout


def test_one_bad_tree_does_not_lose_the_other(tmp_path: Path):
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    good.write_text(json.dumps(trivy_report(vuln())))
    bad.write_text("{{{ truncated")
    result = run(f"ceiling={good}", f"floor={bad}")
    assert result.returncode == 0
    assert "CVE-2026-69244" in result.stdout, "a broken second report must not hide real findings"
    assert "could not be parsed" in result.stdout or "not valid JSON" in result.stdout


def test_parse_trivy_tolerates_missing_and_malformed_nodes():
    assert parse_trivy(None) == []
    assert parse_trivy({"Results": None}) == []
    assert parse_trivy({"Results": [{"Vulnerabilities": None}]}) == []
    assert parse_trivy({"Results": ["not a dict"]}) == []
    assert parse_trivy({"Results": [{"Vulnerabilities": ["not a dict"]}]}) == []


def test_parse_trivy_defaults_missing_fix_version():
    findings = parse_trivy(trivy_report(vuln(FixedVersion="")))
    assert findings[0].fixed == "none available"


def test_pip_audit_is_passed_by_flag_not_position(tmp_path: Path):
    trivy = tmp_path / "trivy.json"
    pa = tmp_path / "pa.json"
    trivy.write_text(json.dumps(clean_report()))
    pa.write_text(json.dumps({"dependencies": [{"name": "x", "version": "1", "vulns": [{"id": "PYSEC-1"}]}]}))
    result = run(str(trivy), "--pip-audit", str(pa))
    assert result.returncode == 0
    assert "PYSEC-1" in result.stdout


def test_parse_pip_audit_marks_severity_unknown():
    doc = {
        "dependencies": [
            {
                "name": "aiohttp",
                "version": "3.12.14",
                "vulns": [{"id": "PYSEC-2026-1", "fix_versions": ["3.14.3"], "aliases": ["CVE-2026-69244"]}],
            }
        ]
    }
    findings = parse_pip_audit(doc)
    assert len(findings) == 1
    assert findings[0].severity == "UNKNOWN"
    assert "CVE-2026-69244" in findings[0].id
    assert findings[0].blocking is False, "pip-audit has no severity, so it must never gate"


def test_parse_pip_audit_tolerates_garbage():
    assert parse_pip_audit({}) == []
    assert parse_pip_audit({"dependencies": "nope"}) == []
    assert parse_pip_audit({"dependencies": [{"vulns": None}]}) == []


# --- merging ----------------------------------------------------------------


def test_merge_dedupes_across_scanners_and_keeps_worst_severity():
    a = Finding("CVE-1", "aiohttp", "3.12.14", "UNKNOWN", "none available", "t", "", "pip-audit")
    b = Finding("CVE-1", "aiohttp", "3.12.14", "HIGH", "3.14.3", "t", "", "trivy")
    merged = merge([[a], [b]])
    assert len(merged) == 1
    assert merged[0].severity == "HIGH"
    assert merged[0].fixed == "3.14.3"
    assert merged[0].sources == {"pip-audit", "trivy"}


def test_merge_sorts_critical_first():
    findings = merge(
        [
            [
                Finding("CVE-LOW", "p", "1", "LOW", "2", "t", "", "trivy"),
                Finding("CVE-CRIT", "p", "1", "CRITICAL", "2", "t", "", "trivy"),
                Finding("CVE-HIGH", "p", "1", "HIGH", "2", "t", "", "trivy"),
            ]
        ]
    )
    assert [f.severity for f in findings] == ["CRITICAL", "HIGH", "LOW"]


# --- injection defences -----------------------------------------------------


def test_pipe_in_package_name_cannot_break_the_table():
    findings = [Finding("CVE-1", "evil|pkg", "1.0", "HIGH", "2.0", "title", "", "trivy")]
    out = render(findings, [], "", blocking=True)
    assert "evil\\|pkg" in out


def test_backticks_in_advisory_text_cannot_escape_the_fence():
    nasty = "benign ``` <script>alert(1)</script> text"
    findings = [Finding("CVE-1", "pkg", "1.0", "HIGH", "2.0", nasty, "", "trivy")]
    out = render(findings, [], "", blocking=True)
    assert "~~~~~~" in out
    # The tilde fence survives a literal ``` inside the advisory body.
    body = out.split("~~~~~~")[1]
    assert "```" in body


def test_non_http_url_is_not_rendered_as_a_link():
    findings = [Finding("CVE-1", "pkg", "1.0", "HIGH", "2.0", "t", "javascript:alert(1)", "trivy")]
    out = render(findings, [], "", blocking=True)
    assert "javascript:" not in out


def test_annotations_escape_newlines_so_they_cannot_forge_commands():
    # GitHub only interprets a ::command:: at the START of a line, so the
    # property that matters is that one finding renders as exactly one line
    # with no raw terminators -- not that the literal text "::error" is absent
    # from the escaped body, which it legitimately can be.
    nasty = "line one\n::error::forged command\rmore"
    findings = [Finding("CVE-1", "pkg", "1.0", "CRITICAL", "2.0", nasty, "", "trivy")]
    out = render_annotations(findings)
    assert "\n" not in out and "\r" not in out, "a raw terminator would let advisory text forge a command"
    assert len([line for line in out.split("\n") if line.startswith("::error")]) == 1
    assert "%0A" in out
    assert "%0D" in out


def test_annotation_percent_escaped_before_newline_markers():
    # If % were escaped after \n, the %0A introduced here would itself become
    # %250A and stop suppressing the newline.
    findings = [Finding("CVE-1", "pkg", "1.0", "CRITICAL", "2.0", "100%\nnext", "", "trivy")]
    out = render_annotations(findings)
    assert "100%25%0Anext" in out


def test_annotations_only_cover_blocking_severities():
    findings = [
        Finding("CVE-LOW", "p", "1", "LOW", "2", "t", "", "trivy"),
        Finding("CVE-MED", "p", "1", "MEDIUM", "2", "t", "", "trivy"),
        Finding("CVE-HIGH", "p", "1", "HIGH", "2", "t", "", "trivy"),
    ]
    out = render_annotations(findings)
    assert "CVE-HIGH" in out
    assert "CVE-LOW" not in out
    assert "CVE-MED" not in out


def test_non_blocking_findings_do_not_claim_to_block():
    findings = [Finding("CVE-1", "p", "1", "MEDIUM", "2", "t", "", "trivy")]
    out = render(findings, [], "", blocking=True)
    assert "does not block" in out


# --- gate semantics ---------------------------------------------------------


def test_unfixable_high_is_reported_but_does_not_block():
    finding = Finding("CVE-1", "pkg", "1.0", "CRITICAL", "none available", "t", "", "trivy")
    assert finding.blocking is False, "an unpatched upstream CVE must not wedge every release"
    out = render([finding], [], "", blocking=True)
    assert "CVE-1" in out, "but it must still be visible in the report"


def test_fixable_high_blocks():
    assert Finding("CVE-1", "pkg", "1.0", "HIGH", "2.0", "t", "", "trivy").blocking is True


def test_gate_exits_1_on_fixable_high(tmp_path: Path):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps(trivy_report(vuln())))
    result = run(str(report), "--gate")
    assert result.returncode == 1
    assert result.stdout == "", "--gate must print nothing to stdout"
    assert "CVE-2026-69244" in result.stderr


def test_gate_exits_0_on_clean(tmp_path: Path):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps(clean_report()))
    result = run(str(report), "--gate")
    assert result.returncode == 0


def test_gate_exits_0_on_unfixable_only(tmp_path: Path):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps(trivy_report(vuln(FixedVersion=""))))
    result = run(str(report), "--gate")
    assert result.returncode == 0


def test_gate_fails_closed_on_unparseable_report(tmp_path: Path):
    bad = tmp_path / "trivy.json"
    bad.write_text("{{{ not json")
    result = run(str(bad), "--gate")
    assert result.returncode == 1, "a scan that did not run must never be reported as a pass"


def test_missing_pip_audit_does_not_fail_the_gate(tmp_path: Path):
    # A pip-audit run that did not finish leaves no report, so "absent" is an
    # expected state. pip-audit is advisory-only and must never gate --
    # otherwise a pip-audit outage blocks every PR and release.
    clean = tmp_path / "trivy.json"
    clean.write_text(json.dumps(clean_report()))
    result = run(str(clean), "--pip-audit", str(tmp_path / "absent.json"), "--gate")
    assert result.returncode == 0


def test_missing_pip_audit_is_named_in_the_report_not_a_parse_failure(tmp_path: Path):
    clean = tmp_path / "trivy.json"
    clean.write_text(json.dumps(clean_report()))
    result = run(str(clean), "--pip-audit", f"runtime-floor={tmp_path / 'absent.json'}")
    assert result.returncode == 0
    assert "pip-audit did not check everything" in result.stdout
    assert "pip-audit:runtime-floor: no report at" in result.stdout
    assert "does not affect the gate" in result.stdout
    assert "could not be parsed" not in result.stdout
    assert (
        "No known vulnerabilities found" in result.stdout
    ), "a missing advisory scanner must not suppress the clean verdict from the gating one"


# --- pip-audit, one report per tree -----------------------------------------


def pip_audit_report(*deps: dict) -> dict:
    return {"dependencies": list(deps), "fixes": []}


def test_pip_audit_is_repeatable_and_tags_findings_with_their_tree(tmp_path: Path):
    trivy = tmp_path / "trivy.json"
    ceiling = tmp_path / "pa-ceiling.json"
    floor = tmp_path / "pa-floor.json"
    trivy.write_text(json.dumps(clean_report()))
    ceiling.write_text(
        json.dumps(pip_audit_report({"name": "werkzeug", "version": "3.1.6", "vulns": [{"id": "PYSEC-2026-2"}]}))
    )
    floor.write_text(
        json.dumps(pip_audit_report({"name": "aiohttp", "version": "3.12.14", "vulns": [{"id": "PYSEC-2026-1"}]}))
    )
    result = run(
        str(trivy),
        "--pip-audit",
        f"runtime-ceiling={ceiling}",
        "--pip-audit",
        f"runtime-floor={floor}",
    )
    assert result.returncode == 0
    assert "**UNKNOWN -- PYSEC-2026-2** (`werkzeug` 3.1.6)\n\nFound by: pip-audit:runtime-ceiling" in result.stdout
    assert "**UNKNOWN -- PYSEC-2026-1** (`aiohttp` 3.12.14)\n\nFound by: pip-audit:runtime-floor" in result.stdout
    assert "pip-audit did not check everything" not in result.stdout


@pytest.mark.parametrize(
    "content,expected",
    [
        ("", "is empty"),
        ("{{{ truncated", "not valid JSON"),
        (json.dumps({}), "lists no audited packages"),
        (json.dumps(pip_audit_report()), "lists no audited packages"),
    ],
)
def test_incomplete_pip_audit_report_is_named(tmp_path: Path, content: str, expected: str):
    trivy = tmp_path / "trivy.json"
    report = tmp_path / "pa.json"
    trivy.write_text(json.dumps(clean_report()))
    report.write_text(content)
    result = run(str(trivy), "--pip-audit", f"dev-ceiling={report}")
    assert result.returncode == 0
    assert result.stdout.split("\n")[0] == MARKER
    assert "pip-audit did not check everything" in result.stdout
    assert "pip-audit:dev-ceiling" in result.stdout
    assert expected in result.stdout


def test_package_pip_audit_skipped_is_named(tmp_path: Path):
    trivy = tmp_path / "trivy.json"
    report = tmp_path / "pa.json"
    trivy.write_text(json.dumps(clean_report()))
    report.write_text(
        json.dumps(
            pip_audit_report(
                {"name": "aiohttp", "version": "3.14.3", "vulns": []},
                {"name": "private-pkg", "skip_reason": "Dependency not found on PyPI and could not be audited"},
            )
        )
    )
    result = run(str(trivy), "--pip-audit", f"runtime-ceiling={report}")
    assert result.returncode == 0
    assert "pip-audit did not check everything" in result.stdout
    assert "pip-audit:runtime-ceiling: skipped private-pkg: Dependency not found on PyPI" in result.stdout


@pytest.mark.parametrize("content", ["", "{{{ truncated", json.dumps({})])
def test_incomplete_pip_audit_never_fails_the_gate(tmp_path: Path, content: str):
    trivy = tmp_path / "trivy.json"
    report = tmp_path / "pa.json"
    trivy.write_text(json.dumps(clean_report()))
    report.write_text(content)
    result = run(str(trivy), "--pip-audit", f"runtime-ceiling={report}", "--gate")
    assert result.returncode == 0
    assert "pip-audit:runtime-ceiling" in result.stderr


@pytest.mark.parametrize(
    "findings,errors",
    [
        ([], []),
        ([Finding("CVE-1", "aiohttp", "1.0", "HIGH", "2.0", "t", "", "trivy")], []),
        ([], ["trivy: boom"]),
    ],
)
def test_slack_names_the_trees_pip_audit_did_not_check(findings, errors):
    gaps = [("pip-audit:runtime-floor", "pip-audit:runtime-floor: no report at /tmp/x.json")]
    lines = render_slack(findings, errors, "https://example.invalid/run", "repo", pip_audit_gaps=gaps).split("\n")
    assert "pip-audit did not fully check pip-audit:runtime-floor" in lines[-2]
    assert lines[-1] == "><https://example.invalid/run|View the full report>"


def test_slack_says_nothing_about_pip_audit_when_it_checked_everything():
    out = render_slack([], [], "", "repo")
    assert "pip-audit" not in out


def test_slack_message_from_cli_names_a_missing_pip_audit_report(tmp_path: Path):
    trivy = tmp_path / "trivy.json"
    trivy.write_text(json.dumps(clean_report()))
    result = run(str(trivy), "--pip-audit", f"runtime-floor={tmp_path / 'absent.json'}", "--slack")
    assert result.returncode == 0
    assert "weekly dependency audit clean" in result.stdout
    assert "pip-audit did not fully check pip-audit:runtime-floor" in result.stdout


# --- an empty scan is not a clean scan --------------------------------------


@pytest.mark.parametrize(
    "doc",
    [
        None,
        {},
        [],
        {"Results": None},
        {"Results": []},
        {"SchemaVersion": 2, "Results": [{"Class": "lang-pkgs"}]},  # Target-less
    ],
)
def test_reports_with_no_scanned_target_are_detected(doc):
    assert trivy_scanned_nothing(doc) is True


def test_real_report_is_not_flagged_as_empty():
    assert trivy_scanned_nothing(trivy_report(vuln())) is False
    assert trivy_scanned_nothing({"Results": [{"Target": "requirements.txt", "Vulnerabilities": []}]}) is False


def test_gate_fails_closed_when_trivy_scanned_nothing(tmp_path: Path):
    # Trivy writes exactly this, with exit code 0, when it recognises no
    # package file -- e.g. the compiled tree was empty or misnamed. Treating
    # it as clean is the single most dangerous silent failure for this gate.
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps({"SchemaVersion": 2, "Results": None}))
    result = run(str(report), "--gate")
    assert result.returncode == 1
    assert "empty scan" in result.stderr or "no scanned package file" in result.stderr


def test_empty_scan_does_not_render_as_clean(tmp_path: Path):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps({"SchemaVersion": 2, "Results": None}))
    result = run(str(report))
    assert result.returncode == 0
    assert "No known vulnerabilities found" not in result.stdout
    assert result.stdout.split("\n")[0] == MARKER


# --- unfixable HIGH/CRITICAL must not be described as absent ----------------


def test_unfixable_critical_is_not_reported_as_none_at_high_or_critical():
    findings = [Finding("CVE-1", "aiohttp", "1.0", "CRITICAL", "none available", "unpatched RCE", "", "trivy")]
    out = render(findings, [], "", blocking=True)
    assert (
        "none at HIGH or CRITICAL" not in out
    ), "the severity table directly below says CRITICAL 1; the headline must not contradict it"
    assert "no fix available" in out
    assert "CRITICAL" in out


def test_unfixable_critical_slack_message_is_not_reassuring():
    findings = [Finding("CVE-1", "aiohttp", "1.0", "CRITICAL", "none available", "unpatched RCE", "", "trivy")]
    out = render_slack(findings, [], "", "repo")
    assert "none HIGH/CRITICAL" not in out
    assert ":rotating_light:" in out
    assert "aiohttp" in out


def test_mixed_fixable_and_unfixable_reports_both_counts():
    findings = [
        Finding("CVE-FIX", "a", "1.0", "HIGH", "2.0", "t", "", "trivy"),
        Finding("CVE-NOFIX", "b", "1.0", "CRITICAL", "none available", "t", "", "trivy"),
    ]
    out = render(findings, [], "", blocking=True)
    assert "1 fixable HIGH/CRITICAL" in out
    assert "no fix available yet" in out
