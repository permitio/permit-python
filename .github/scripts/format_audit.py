#!/usr/bin/env python3
"""Render scanner JSON as a markdown PR comment (and GitHub annotations).

Reads a Trivy JSON report and, optionally, a pip-audit JSON report, and writes a
single markdown body to stdout for the audit workflow to post as a sticky PR
comment.

Contract (the workflow depends on every line of this):

* stdout is the markdown body and nothing else; diagnostics go to stderr.
* The marker is the literal first line of *every* output state -- clean,
  vulnerable, and parse-failure alike. The workflow finds its previous comment
  by that prefix, so an output state that omitted it would post a second
  comment beside the stale one instead of replacing it.
* Exit code is 0 for every input except a missing CLI argument (2). Garbage,
  truncated JSON and empty files all still produce a complete marker-prefixed
  body. The workflow only posts when this script exits 0, so failing on bad
  input would silently strip the PR of its only signal.

Stdlib only: this runs on a bare actions/setup-python with nothing installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MARKER = "<!-- permit-python:audit:deps -->"

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
BLOCKING_SEVERITIES = {"CRITICAL", "HIGH"}

# Sentinel used wherever a scanner reports no fixed version.
NO_FIX = "none available"

SEVERITY_EMOJI = {
    "CRITICAL": ":bangbang:",
    "HIGH": ":red_circle:",
    "MEDIUM": ":large_orange_diamond:",
    "LOW": ":white_circle:",
    "UNKNOWN": ":grey_question:",
}

# Six tildes rather than triple backticks. Advisory text is third-party content
# and a literal ``` inside it would close a backtick fence and let the rest of
# the string render as markdown/HTML in the comment and the job summary.
FENCE = "~~~~~~"

# GitHub truncates annotation text; cut it ourselves so the ellipsis is visible.
_ANNOTATION_MAX_CHARS = 200
# The Slack message is two header lines, then one line per package.
_SLACK_HEADER_LINES = 2
_SLACK_MAX_PACKAGES = 10


class Finding:
    """One vulnerability, normalized across scanners."""

    def __init__(  # noqa: PLR0917 - one field per scanner column; built positionally
        self,
        vuln_id: str,
        package: str,
        installed: str,
        severity: str,
        fixed: str,
        title: str,
        url: str,
        source: str,
    ) -> None:
        self.id = vuln_id
        self.package = package
        self.installed = installed
        self.severity = severity if severity in SEVERITY_ORDER else "UNKNOWN"
        self.fixed = fixed
        self.title = title
        self.url = url
        self.sources = {source}

    @property
    def key(self) -> tuple[str, str]:
        """Identity used to merge the same advisory reported by several scanners."""
        return (self.package, self.id)

    @property
    def blocking(self) -> bool:
        """HIGH/CRITICAL *with a fix available*.

        An advisory nobody has patched yet cannot be fixed by bumping a bound,
        so blocking on it would wedge every release until upstream moves --
        the equivalent of Trivy's --ignore-unfixed. It still appears in the
        report; it just does not gate.
        """
        return self.severity in BLOCKING_SEVERITIES and self.fixed != NO_FIX


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _md_cell(text: str) -> str:
    """Make a string safe to drop into a markdown table cell."""
    return _truncate(text, 140).replace("|", "\\|").replace("`", "'")


def _load(path: str | None, label: str) -> tuple[Any | None, str | None]:
    """Return (parsed, error). Never raises -- a bad report must not kill the run."""
    if not path:
        return None, None
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"{label}: could not read {path}: {exc}"
    if not raw.strip():
        return None, f"{label}: {path} is empty"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, f"{label}: {path} is not valid JSON: {exc}"


def trivy_scanned_nothing(doc: object) -> bool:
    """True when Trivy produced no package Result at all.

    Trivy writes {"Results": null} and exits 0 when it recognises no package
    file -- which is exactly what happens if the compiled tree is missing,
    empty, or written under a name its pip analyzer does not match. That is
    indistinguishable from a clean scan by findings alone, so it is detected
    explicitly and treated as a failure rather than a pass.
    """
    if not isinstance(doc, dict):
        return True
    results = doc.get("Results")
    if not isinstance(results, list) or not results:
        return True
    return not any(isinstance(r, dict) and r.get("Target") for r in results)


def parse_trivy(doc: object, source: str = "trivy") -> list[Finding]:
    """Extract the findings of a Trivy JSON report; malformed entries are skipped."""
    findings: list[Finding] = []
    if not isinstance(doc, dict):
        return findings
    for result in doc.get("Results") or []:
        if not isinstance(result, dict):
            continue
        for vuln in result.get("Vulnerabilities") or []:
            if not isinstance(vuln, dict):
                continue
            fixed = vuln.get("FixedVersion") or ""
            findings.append(
                Finding(
                    vuln_id=str(vuln.get("VulnerabilityID") or "UNKNOWN"),
                    package=str(vuln.get("PkgName") or "unknown"),
                    installed=str(vuln.get("InstalledVersion") or "?"),
                    severity=str(vuln.get("Severity") or "UNKNOWN").upper(),
                    fixed=str(fixed) or NO_FIX,
                    title=str(vuln.get("Title") or vuln.get("Description") or ""),
                    url=str(vuln.get("PrimaryURL") or ""),
                    source=source,
                )
            )
    return findings


def parse_pip_audit(doc: object) -> list[Finding]:
    """pip-audit carries no severity at all, so everything lands in UNKNOWN.

    That is why pip-audit is advisory-only here and never gates the build: it
    cannot distinguish a critical from a nuisance. It earns its place by
    reading PYSEC, which occasionally publishes a Python-specific advisory
    before it reaches the GHSA feed Trivy uses.
    """
    findings: list[Finding] = []
    deps = doc.get("dependencies") if isinstance(doc, dict) else doc
    if not isinstance(deps, list):
        return findings
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        name = str(dep.get("name") or "unknown")
        version = str(dep.get("version") or "?")
        for vuln in dep.get("vulns") or []:
            if not isinstance(vuln, dict):
                continue
            fixes = vuln.get("fix_versions") or []
            fixed = (
                ", ".join(str(f) for f in fixes) if isinstance(fixes, list) and fixes else NO_FIX
            )
            aliases = vuln.get("aliases") or []
            alias_str = ""
            if isinstance(aliases, list) and aliases:
                alias_str = f" ({', '.join(str(a) for a in aliases[:3])})"
            findings.append(
                Finding(
                    vuln_id=str(vuln.get("id") or "UNKNOWN") + alias_str,
                    package=name,
                    installed=version,
                    severity="UNKNOWN",
                    fixed=fixed,
                    title=str(vuln.get("description") or ""),
                    url="",
                    source="pip-audit",
                )
            )
    return findings


def merge(groups: list[list[Finding]]) -> list[Finding]:
    """Dedupe across scanners, keeping the most severe view of each finding."""
    merged: dict[tuple[str, str], Finding] = {}
    for group in groups:
        for finding in group:
            existing = merged.get(finding.key)
            if existing is None:
                merged[finding.key] = finding
                continue
            existing.sources |= finding.sources
            if SEVERITY_ORDER.index(finding.severity) < SEVERITY_ORDER.index(existing.severity):
                existing.severity = finding.severity
            if existing.fixed == NO_FIX and finding.fixed != NO_FIX:
                existing.fixed = finding.fixed
    return sorted(
        merged.values(),
        key=lambda f: (SEVERITY_ORDER.index(f.severity), f.package, f.id),
    )


def _annotation_escape(text: str) -> str:
    """Escape a value for a ::error:: workflow command.

    A raw newline would end the command early and let the remainder of an
    advisory string be interpreted as its own workflow command. This escapes
    the line terminators itself rather than leaning on _truncate happening to
    collapse whitespace -- the safety of the output must not depend on an
    unrelated helper's incidental behaviour.

    Order matters: % is escaped first, or it would corrupt the %0D/%0A the
    later replacements introduce.
    """
    text = str(text)
    text = text if len(text) <= _ANNOTATION_MAX_CHARS else text[: _ANNOTATION_MAX_CHARS - 1] + "…"
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def render_annotations(findings: list[Finding]) -> str:
    """Render one GitHub `::error` workflow command per blocking finding."""
    lines = []
    for finding in findings:
        if not finding.blocking:
            continue
        title = _annotation_escape(f"{finding.severity}: {finding.id} in {finding.package}")
        body = _annotation_escape(
            f"{finding.package} {finding.installed} -- fixed in {finding.fixed}. {finding.title}"
        )
        lines.append(f"::error title={title}::{body}")
    return "\n".join(lines)


def _slack_escape(text: str) -> str:
    """Slack requires these three to be entity-escaped inside message text."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_slack(findings: list[Finding], errors: list[str], run_url: str, repo: str) -> str:
    """One line of Slack `text`, carrying the findings rather than a verdict.

    A scheduled run has no PR to comment on, so this is the only channel that
    reaches a person. Saying only "the audit failed" would make them open the
    run to learn anything at all, so the packages, counts and upgrade targets
    go in the message itself.
    """
    link = f"<{run_url}|View the full report>" if run_url else "See the workflow run."

    if errors:
        return (
            f":warning: *{_slack_escape(repo)} — weekly dependency audit could not complete*\n"
            f">A scanner report could not be parsed, so the tree was not fully scanned. "
            f"A clean history is not evidence of a clean tree.\n>{link}"
        )

    blockers = [f for f in findings if f.blocking]
    severe = [f for f in findings if f.severity in BLOCKING_SEVERITIES]
    if not findings:
        return (
            f":white_check_mark: *{_slack_escape(repo)} — weekly dependency audit clean*\n"
            f">No known advisories in either the resolved tree or the lowest versions "
            f"the published specs permit.\n>{link}"
        )

    # Collapse to one line per package: a package with 30 advisories should not
    # produce 30 Slack lines.
    by_package: dict[str, list[Finding]] = {}
    for finding in blockers or severe or findings:
        by_package.setdefault(finding.package, []).append(finding)

    icon = ":rotating_light:" if severe else ":large_orange_diamond:"
    if blockers:
        headline = f"*{len(blockers)} fixable HIGH/CRITICAL* advisories"
    elif severe:
        headline = f"*{len(severe)} HIGH/CRITICAL* with no fix available yet"
    else:
        headline = f"{len(findings)} advisories, none HIGH/CRITICAL"
    lines = [f"{icon} *{_slack_escape(repo)} — weekly dependency audit*", f">{headline}."]

    for package in sorted(by_package):
        group = by_package[package]
        worst = min(group, key=lambda f: SEVERITY_ORDER.index(f.severity))
        # Highest fix target across the group -- upgrading to anything lower
        # would leave part of the group unresolved.
        targets = sorted({f.fixed for f in group if f.fixed != NO_FIX})
        target = (
            f" — upgrade to `{_slack_escape(targets[-1])}`" if targets else " — no fix available"
        )
        installed = _slack_escape(worst.installed)
        lines.append(
            f">• `{_slack_escape(package)}` {installed} — "
            f"{len(group)} {'advisory' if len(group) == 1 else 'advisories'} "
            f"({worst.severity} worst){target}"
        )

    # Slack truncates long messages; keep it to something a human will read.
    if len(lines) > _SLACK_HEADER_LINES + _SLACK_MAX_PACKAGES:
        lines = [
            *lines[: _SLACK_HEADER_LINES + _SLACK_MAX_PACKAGES],
            f">…and {len(by_package) - _SLACK_MAX_PACKAGES} more packages.",
        ]

    lines.append(f">{link}")
    return "\n".join(lines)


def _advisory_link(finding: Finding) -> str:
    if finding.url.startswith("http"):
        return f"[{_md_cell(finding.id)}]({finding.url})"
    return _md_cell(finding.id)


def render(  # noqa: C901, PLR0915 - one linear pass appending each report section
    findings: list[Finding],
    errors: list[str],
    context: str,
    *,
    blocking: bool,
    warnings: list[str] | None = None,
) -> str:
    """Render the markdown PR comment body."""
    out: list[str] = [MARKER, "", "## Dependency Security Audit", ""]

    if context:
        out.append(f"_Scanned: {context}_")
        out.append("")

    if errors:
        out.append(":x: **One or more scanner reports could not be parsed.**")
        out.append("")
        out.append("The audit did not complete cleanly, so this report may be incomplete.")
        out.append("")
        out.append(FENCE)
        out.extend(errors)
        out.append(FENCE)
        out.append("")

    if warnings:
        out.append(":information_source: Advisory scanner notes (these do not affect the gate):")
        out.append("")
        out.append(FENCE)
        out.extend(warnings)
        out.append(FENCE)
        out.append("")

    if not findings:
        if not errors:
            out.append(":white_check_mark: **No known vulnerabilities found.**")
            out.append("")
            out.append(
                "Both the resolved dependency set and the lowest versions the published "
                "specs permit are clean at HIGH and CRITICAL."
            )
        return "\n".join(out) + "\n"

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1

    blockers = [f for f in findings if f.blocking]
    severe = [f for f in findings if f.severity in BLOCKING_SEVERITIES]
    unfixable = len(severe) - len(blockers)
    if blockers:
        verb = "blocking this build" if blocking else "reported (gate is advisory)"
        noun = "advisory" if len(blockers) == 1 else "advisories"
        out.append(f":x: **{len(blockers)} fixable HIGH/CRITICAL {noun}** -- {verb}.")
        if unfixable:
            out.append("")
            out.append(
                f":warning: A further **{unfixable}** HIGH/CRITICAL have no fix available yet "
                "and do not block."
            )
    elif severe:
        # Do not say "none at HIGH or CRITICAL" here: there are some, they
        # just cannot be fixed by bumping a bound. Saying otherwise would
        # contradict the severity table printed directly below.
        out.append(
            f":warning: **{len(severe)} HIGH/CRITICAL** with no fix available yet. "
            "These do not block the build, because no version bump can resolve them -- "
            "but they are real exposure and need a decision."
        )
    else:
        out.append(
            ":warning: Advisories found, but none at HIGH or CRITICAL. "
            "This does not block the build."
        )
    out.append("")

    out.append("| Severity | Count |")
    out.append("| --- | --- |")
    out.extend(
        f"| {SEVERITY_EMOJI[severity]} {severity} | {counts[severity]} |"
        for severity in SEVERITY_ORDER
        if counts.get(severity)
    )
    out.append("")

    out.append("| Severity | Package | Installed | Fixed in | Advisory |")
    out.append("| --- | --- | --- | --- | --- |")
    out.extend(
        f"| {SEVERITY_EMOJI[finding.severity]} {finding.severity} "
        f"| `{_md_cell(finding.package)}` "
        f"| `{_md_cell(finding.installed)}` "
        f"| `{_md_cell(finding.fixed)}` "
        f"| {_advisory_link(finding)} |"
        for finding in findings
    )
    out.append("")

    out.append("<details><summary>Advisory details</summary>")
    out.append("")
    for finding in findings:
        out.append(
            f"**{finding.severity} -- {finding.id}** (`{finding.package}` {finding.installed})"
        )
        out.append("")
        out.append(f"Found by: {', '.join(sorted(finding.sources))}")
        out.append("")
        if finding.title:
            out.append(FENCE)
            out.append(_truncate(finding.title, 1200))
            out.append(FENCE)
        out.append("")
    out.append("</details>")
    out.append("")

    out.append("### How to fix")
    out.append("")
    out.append(
        "Raise the affected lower bound in `pyproject.toml` (`[project].dependencies`, or the "
        "pin in the `dev` dependency group) to at least the *Fixed in* version above, then "
        "run `uv lock`. Because this package publishes open "
        "`>=` ranges, the floor is what consumers can actually install -- bumping only the "
        "resolved version does not close the hole."
    )
    out.append("")
    out.append(
        "An advisory with no fix available does not block the build -- it is reported "
        "here so it can be tracked, but no version bump can resolve it. Suppression "
        "files are deliberately not honoured: the scan runs with `--ignorefile "
        "/dev/null` so nothing can disappear from this report silently."
    )

    return "\n".join(out) + "\n"


def main() -> int:  # noqa: C901, PLR0912 - argument handling, then one pass per output mode
    """Parse the scanner reports and print the requested output; return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "trivy_json",
        nargs="+",
        help=(
            "Trivy JSON report(s). Accepts LABEL=PATH to tag findings with the "
            "dependency tree they came from (e.g. floor=/tmp/floor.json), which is "
            "how one comment can cover both the resolved set and the lowest "
            "versions the published specs permit."
        ),
    )
    parser.add_argument("--pip-audit", dest="pip_audit_json", help="optional pip-audit JSON report")
    parser.add_argument("--context", default="", help="human label for what was scanned")
    parser.add_argument(
        "--annotations",
        action="store_true",
        help="emit ::error:: workflow commands for HIGH/CRITICAL instead of markdown",
    )
    parser.add_argument(
        "--blocking",
        action="store_true",
        help="word the report as gating the build rather than advisory",
    )
    parser.add_argument(
        "--slack",
        action="store_true",
        help="emit a single-line Slack message body carrying the findings",
    )
    parser.add_argument(
        "--run-url", default="", help="workflow run URL to link from the Slack message"
    )
    parser.add_argument(
        "--repo", default="permit-python", help="repository name for the Slack message"
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help=(
            "exit 1 if any fixable HIGH/CRITICAL advisory is present, printing nothing. "
            "Keeps the pass/fail decision in the same unit-tested place as the report, "
            "so the comment and the check can never disagree."
        ),
    )
    args = parser.parse_args()

    errors: list[str] = []
    groups: list[list[Finding]] = []

    for spec in args.trivy_json:
        label, sep, path = spec.partition("=")
        if not sep:
            label, path = "trivy", spec
        else:
            label = f"trivy:{label}"
        doc, err = _load(path, label)
        if err:
            errors.append(err)
        elif trivy_scanned_nothing(doc):
            errors.append(
                f"{label}: the report contains no scanned package file. Trivy exits 0 when it "
                "recognises nothing to scan, so this is an empty scan, not a clean one."
            )
        groups.append(parse_trivy(doc, source=label))

    # pip-audit problems are warnings, never errors. It is advisory-only and
    # never gates, so letting it fail the gate closed would mean an unrelated
    # pip-audit outage blocks every PR and release. audit-deps.sh deliberately
    # deletes a partial pip-audit report, so "missing" is an expected state.
    pip_doc, pip_err = _load(args.pip_audit_json, "pip-audit")
    warnings: list[str] = []
    if pip_err:
        warnings.append(pip_err)
    groups.append(parse_pip_audit(pip_doc))

    findings = merge(groups)

    for err in errors + warnings:
        print(err, file=sys.stderr)

    if args.slack:
        print(render_slack(findings, errors, args.run_url, args.repo))
        return 0

    if args.gate:
        blockers = [f for f in findings if f.blocking]
        for finding in blockers:
            print(
                f"{finding.severity} {finding.id} {finding.package} "
                f"{finding.installed} -> {finding.fixed}",
                file=sys.stderr,
            )
        if errors:
            print("refusing to pass: a scanner report could not be parsed", file=sys.stderr)
            return 1
        return 1 if blockers else 0

    if args.annotations:
        rendered = render_annotations(findings)
        if rendered:
            print(rendered)
        return 0

    sys.stdout.write(
        render(findings, errors, args.context, blocking=args.blocking, warnings=warnings)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
