#!/usr/bin/env python3
"""Report which Permit API operations the SDK covers, from the requests its tests send.

PER-16336 section 7, for permit-python (PER-16337).

Where the numbers come from:

* The operations are those of two OpenAPI documents: the control plane's
  (https://api.permit.io/v2/openapi.json) and the container PDP's (served at
  /openapi.json by the PDP image test.yml pins). Pull requests read the operation
  inventories committed under .github/api-specs/, so their result depends only on the
  commit. The weekly job reads the live control-plane spec instead.
* What the SDK calls comes from a record of the requests the offline tests actually
  sent (tests/api_coverage_recorder.py writes it). Each request's method and path is
  matched to an operation's path template; the template with the most literal segments
  wins. An operation is covered when an offline test sent a request that matches it, so
  an SDK method that no offline test calls does not count.
* The end-to-end column comes from the records of the e2e runs, when there are any: an
  operation is exercised end to end when an e2e test got a 2xx or 3xx answer from it.
  With no e2e record the column says "not run", never "no".

Every operation is covered, allowlisted, or missing. The allowlist
(.github/scripts/api_coverage_allowlist.json) gives each operation left out on purpose a
status and one reason: `excluded` (out of scope for the SDK), `deferred` (planned, with
its ticket) or `untested` (an SDK method calls it, but no offline test sends the request
yet). A request that matches no operation in either spec is SDK-only; the allowlist's
`sdk_only` entries explain the known ones. An operation's stage is `deprecated` when the
spec says so, `EAP` when one of its tags names EAP, and `GA` otherwise.

The report fails (exit 1) on:

* a GA operation that is neither covered nor allowlisted;
* a stale allowlist entry: its operation is covered now, or is not in the spec;
* a changed operation: an entry whose recorded stage is not the spec's stage;
* an SDK-only request that no `sdk_only` entry explains, or an `sdk_only` entry that no
  request matches.

EAP and deprecated operations that are neither covered nor allowlisted are listed, but do
not fail the report. Request and response shapes are the Schema Drift check's job
(.github/workflows/schema-drift.yml), not this one's.

Contract (the workflows depend on it):

* Exit 0: none of the failures above. Exit 1: at least one of them.
* Exit 2: the report did not run, and is never reported as clean. That is a spec that
  cannot be read or lists fewer operations than its minimum, an invalid allowlist, a
  request record that is missing, malformed, from a session that did not finish or that
  failed, or that holds fewer offline requests than the minimum, or any other error.
* The Markdown report goes to --summary (default stdout), the full result as JSON to
  --json, and --github-output receives the failure counts.

The `snapshot` subcommand writes the operation inventory of a downloaded spec, and its
source and fetch date next to it, which is how the committed snapshots are refreshed.

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

CONTROL_PLANE = "control-plane"
PDP = "pdp"
APIS = (CONTROL_PLANE, PDP)
API_TITLES = {CONTROL_PLANE: "Control plane", PDP: "PDP"}

GA = "GA"
EAP = "EAP"
DEPRECATED = "deprecated"
STAGES = (GA, EAP, DEPRECATED)

COVERED = "covered"
MISSING = "missing"
EXCLUDED = "excluded"
DEFERRED = "deferred"
UNTESTED = "untested"
ALLOWLIST_STATUSES = (EXCLUDED, DEFERRED, UNTESTED)

UNDOCUMENTED = "undocumented"
TEST_ONLY = "test-only"
SDK_ONLY_STATUSES = (UNDOCUMENTED, TEST_ONLY)

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")
EAP_TAG = re.compile(r"\bEAP\b")
TICKET = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
PARAMETER = re.compile(r"\{[^/{}]*\}")

# The request record format tests/api_coverage_recorder.py writes.
RECORD_VERSION = 1
# Far below what the suite sends today (about 590 requests), so the sentinel only trips
# when the record is truncated or the recorder stopped seeing requests.
DEFAULT_MIN_RECORDS = 400
# Far below today's counts (263 and 34), for the same reason.
DEFAULT_MIN_OPERATIONS = {CONTROL_PLANE: 200, PDP: 20}
# How many test ids the JSON report keeps per operation.
TESTS_PER_OPERATION = 5
SUCCESS_STATUSES = range(200, 400)


class CoverageError(Exception):
    """The report could not run. Maps to exit code 2."""


# --- specs --------------------------------------------------------------------


def normalize(path: str) -> str:
    """A path template with its parameter names dropped: `/users/{user_id}` is `/users/{}`."""
    return PARAMETER.sub("{}", path)


def template_pattern(path: str) -> re.Pattern[str]:
    """A regular expression that matches the concrete paths of a path template.

    A parameter matches one non-empty path segment. The request path is matched still
    percent-encoded, so a `%2F` inside a key stays inside its segment.
    """
    parts = PARAMETER.split(path)
    return re.compile("[^/]+".join(re.escape(part) for part in parts) + r"\Z")


def specificity(path: str) -> tuple[int, ...]:
    """Rank a path template: literal segments beat parameters, from the left."""
    return tuple(0 if PARAMETER.fullmatch(segment) else 1 for segment in path.split("/"))


def stage_of(operation: dict[str, Any]) -> str:
    """The stage of a spec operation: deprecated, EAP (a tag that names EAP) or GA."""
    if operation.get("deprecated") is True:
        return DEPRECATED
    if any(EAP_TAG.search(str(tag)) for tag in operation.get("tags") or []):
        return EAP
    return GA


@dataclass(frozen=True)
class Operation:
    """One operation of a spec: an HTTP method on a path template."""

    api: str
    method: str
    path: str
    stage: str
    tags: tuple[str, ...]
    summary: str
    pattern: re.Pattern[str] = field(compare=False, repr=False)

    @property
    def name(self) -> str:
        """How the report and the allowlist write the operation: `GET /v2/...`."""
        return f"{self.method} {self.path}"

    @property
    def key(self) -> tuple[str, str, str]:
        """The operation's identity: its API, method and path with parameter names dropped."""
        return (self.api, self.method, normalize(self.path))


@dataclass
class Spec:
    """The operations of one API, and where they were read from."""

    api: str
    source: str
    operations: list[Operation]

    def match(self, method: str, path: str) -> Operation | None:
        """The operation a request's method and path belong to, if any."""
        candidates = [
            op for op in self.operations if op.method == method and op.pattern.match(path)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda op: (specificity(op.path), op.path))


def read_json(path: Path, what: str) -> Any:  # noqa: ANN401 - whatever the JSON document holds
    """Read a JSON file.

    Raises:
        CoverageError: If the file cannot be read or is not JSON.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"could not read {what} at {path}: {exc}"
        raise CoverageError(msg) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        msg = f"{what} at {path} is not valid JSON: {exc}"
        raise CoverageError(msg) from exc


def operations_of(document: Any, api: str, label: str) -> list[Operation]:  # noqa: ANN401
    """List the operations of an OpenAPI document or of a committed operation inventory.

    Raises:
        CoverageError: If the document has no `paths` object, or two operations share a
            method and a path that differ only in parameter names.
    """
    paths = document.get("paths") if isinstance(document, dict) else None
    if not isinstance(paths, dict):
        msg = f"{label} has no `paths` object"
        raise CoverageError(msg)
    operations: list[Operation] = []
    seen: dict[tuple[str, str, str], str] = {}
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            spec_operation = item.get(method)
            if not isinstance(spec_operation, dict):
                continue
            operation = Operation(
                api=api,
                method=method.upper(),
                path=str(path),
                stage=stage_of(spec_operation),
                tags=tuple(str(tag) for tag in spec_operation.get("tags") or []),
                summary=str(spec_operation.get("summary") or ""),
                pattern=template_pattern(str(path)),
            )
            if operation.key in seen:
                msg = f"{label}: {operation.name} and {seen[operation.key]} are the same operation"
                raise CoverageError(msg)
            seen[operation.key] = operation.name
            operations.append(operation)
    return operations


def load_spec(api: str, path: Path, minimum: int) -> Spec:
    """Read one API's spec and check it lists at least `minimum` operations.

    Raises:
        CoverageError: If the spec cannot be read, or lists fewer operations than
            `minimum`.
    """
    label = f"the {API_TITLES[api]} spec"
    operations = operations_of(read_json(path, label), api, f"{label} at {path}")
    if len(operations) < minimum:
        msg = (
            f"{label} at {path} lists {len(operations)} operations, fewer than the "
            f"minimum of {minimum}; it is truncated or not the spec"
        )
        raise CoverageError(msg)
    return Spec(api=api, source=_describe_source(path), operations=operations)


def _describe_source(path: Path) -> str:
    """Name a spec by its file, and by the source and date its sidecar records."""
    sidecar = path.with_name(path.name.removesuffix(".json") + ".source.json")
    if not sidecar.is_file():
        return f"`{path}`"
    try:
        source = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return f"`{path}`"
    if not isinstance(source, dict):
        return f"`{path}`"
    return f"`{path}`, a snapshot of {source.get('source')} taken {source.get('fetched')}"


# --- request records ----------------------------------------------------------


@dataclass(frozen=True)
class Request:
    """One recorded request."""

    method: str
    path: str
    status: int | None
    test: str
    e2e: bool


@dataclass
class Record:
    """A request record: the requests one test session sent, and how the session ended."""

    path: Path
    requests: list[Request]
    exitstatus: int
    tests: int


def load_record(path: Path) -> Record:
    """Read a request record written by tests/api_coverage_recorder.py.

    Raises:
        CoverageError: If the file cannot be read, a line is malformed, the format
            version is not this script's, or the session line is missing (the session
            did not finish).
    """
    lines = _record_lines(path)
    header = _record_line(path, 1, lines[0])
    if header.get("kind") != "header" or header.get("version") != RECORD_VERSION:
        msg = (
            f"the request record {path} does not start with a version {RECORD_VERSION} "
            f"header: {lines[0][:200]}"
        )
        raise CoverageError(msg)
    requests: list[Request] = []
    session: dict[str, Any] | None = None
    for number, text in enumerate(lines[1:], start=2):
        line = _record_line(path, number, text)
        if session is not None:
            msg = f"the request record {path} continues after its session line (line {number})"
            raise CoverageError(msg)
        if line.get("kind") == "request":
            requests.append(_request(path, number, line))
        elif line.get("kind") == "session":
            session = line
        else:
            msg = f"line {number} of the request record {path} has an unknown kind"
            raise CoverageError(msg)
    if session is None:
        msg = f"the request record {path} has no session line: the test session did not finish"
        raise CoverageError(msg)
    exitstatus, tests = session.get("exitstatus"), session.get("tests")
    if not isinstance(exitstatus, int) or not isinstance(tests, int):
        msg = f"the session line of the request record {path} is malformed"
        raise CoverageError(msg)
    return Record(path=path, requests=requests, exitstatus=exitstatus, tests=tests)


def _record_lines(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        msg = f"could not read the request record {path}: {exc}"
        raise CoverageError(msg) from exc
    except UnicodeDecodeError as exc:
        msg = f"the request record {path} is not UTF-8 text: {exc}"
        raise CoverageError(msg) from exc
    if not lines:
        msg = f"the request record {path} is empty; the recorder never ran"
        raise CoverageError(msg)
    return lines


def _record_line(path: Path, number: int, text: str) -> dict[str, Any]:
    try:
        line = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"line {number} of the request record {path} is not JSON: {exc}"
        raise CoverageError(msg) from exc
    if not isinstance(line, dict):
        msg = f"line {number} of the request record {path} is not a JSON object"
        raise CoverageError(msg)
    return line


def _request(path: Path, number: int, line: dict[str, Any]) -> Request:
    method, request_path, status = line.get("method"), line.get("path"), line.get("status")
    test, e2e = line.get("test"), line.get("e2e")
    if (
        not isinstance(method, str)
        or not isinstance(request_path, str)
        or not request_path.startswith("/")
        or not (status is None or isinstance(status, int))
        or not isinstance(test, str | None)
        or not isinstance(e2e, bool)
    ):
        msg = f"line {number} of the request record {path} is not a well-formed request"
        raise CoverageError(msg)
    return Request(method.upper(), request_path, status, test or "(outside any test)", e2e)


def check_offline_record(record: Record, minimum: int) -> list[Request]:
    """The offline requests of a record, once the record has passed its sentinels.

    Raises:
        CoverageError: If the session failed, or sent fewer offline requests than
            `minimum`.
    """
    if record.exitstatus != 0:
        msg = (
            f"the offline test session that wrote {record.path} exited {record.exitstatus}, "
            "so its record is not a complete account of what the tests send"
        )
        raise CoverageError(msg)
    offline = [request for request in record.requests if not request.e2e]
    if len(offline) < minimum:
        msg = (
            f"the request record {record.path} holds {len(offline)} offline requests, fewer "
            f"than the minimum of {minimum}; the recorder missed requests or tests did not run"
        )
        raise CoverageError(msg)
    return offline


# --- allowlist ----------------------------------------------------------------


@dataclass(frozen=True)
class OperationEntry:
    """An operation left uncovered on purpose."""

    api: str
    method: str
    path: str
    stage: str
    status: str
    reason: str
    ticket: str

    @property
    def name(self) -> str:
        """The operation as the allowlist writes it."""
        return f"{self.method} {self.path}"

    @property
    def key(self) -> tuple[str, str, str]:
        """The identity of the operation the entry is about (see Operation.key)."""
        return (self.api, self.method, normalize(self.path))


@dataclass(frozen=True)
class SdkOnlyEntry:
    """A request that matches no spec operation, and why the SDK sends it."""

    method: str
    path: str
    status: str
    reason: str
    ticket: str
    pattern: re.Pattern[str] = field(compare=False, repr=False)

    @property
    def name(self) -> str:
        """The request as the allowlist writes it."""
        return f"{self.method} {self.path}"


@dataclass
class Allowlist:
    """The operation and SDK-only entries of the allowlist."""

    operations: list[OperationEntry]
    sdk_only: list[SdkOnlyEntry]


def _split_name(text: object, where: str) -> tuple[str, str]:
    if not isinstance(text, str):
        msg = f"{where} needs a string naming the request, such as `GET /v2/...`"
        raise CoverageError(msg)
    method, _, path = text.partition(" ")
    if method not in {m.upper() for m in HTTP_METHODS}:
        msg = f"{where}: {text!r} does not start with an upper-case HTTP method"
        raise CoverageError(msg)
    if not path.startswith("/") or " " in path:
        msg = f"{where}: {text!r} does not name a path after the method"
        raise CoverageError(msg)
    return method, path


def _text(raw: dict[str, Any], key: str, where: str, *, required: bool = True) -> str:
    value = raw.get(key, "")
    if not isinstance(value, str) or (required and not value.strip()):
        msg = f'{where} needs a non-empty string "{key}"'
        raise CoverageError(msg)
    return value


def _choice(raw: dict[str, Any], key: str, choices: Sequence[str], where: str) -> str:
    value = raw.get(key)
    if value not in choices:
        msg = f'{where}: "{key}" must be one of {", ".join(choices)}, not {value!r}'
        raise CoverageError(msg)
    return str(value)


def _ticket(raw: dict[str, Any], where: str, *, required: bool) -> str:
    ticket = _text(raw, "ticket", where, required=required)
    if ticket and not TICKET.match(ticket):
        msg = f"{where}: ticket {ticket!r} is not a ticket id such as PER-123"
        raise CoverageError(msg)
    return ticket


def _entries(doc: dict[str, Any], key: str, path: Path) -> list[dict[str, Any]]:
    raw = doc.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        msg = f'the allowlist {path} needs a "{key}" list of objects'
        raise CoverageError(msg)
    return raw


def load_allowlist(path: Path) -> Allowlist:
    """Read and validate the allowlist.

    Raises:
        CoverageError: If the file is missing or not JSON, or an entry lacks a field,
            uses an unknown value, repeats another entry, or (for `deferred`) names no
            ticket.
    """
    doc = read_json(path, "the allowlist")
    if not isinstance(doc, dict):
        msg = f"the allowlist {path} is not a JSON object"
        raise CoverageError(msg)
    operations: list[OperationEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(_entries(doc, "operations", path)):
        where = f"allowlist operation entry {index}"
        method, op_path = _split_name(raw.get("operation"), where)
        status = _choice(raw, "status", ALLOWLIST_STATUSES, where)
        entry = OperationEntry(
            api=_choice(raw, "api", APIS, where),
            method=method,
            path=op_path,
            stage=_choice(raw, "stage", STAGES, where),
            status=status,
            reason=_text(raw, "reason", where),
            ticket=_ticket(raw, where, required=status == DEFERRED),
        )
        if entry.key in seen:
            msg = f"{where}: {entry.api} {entry.name} is listed more than once"
            raise CoverageError(msg)
        seen.add(entry.key)
        operations.append(entry)
    sdk_only: list[SdkOnlyEntry] = []
    seen_requests: set[tuple[str, str]] = set()
    for index, raw in enumerate(_entries(doc, "sdk_only", path)):
        where = f"allowlist sdk_only entry {index}"
        method, request_path = _split_name(raw.get("request"), where)
        status = _choice(raw, "status", SDK_ONLY_STATUSES, where)
        if (method, normalize(request_path)) in seen_requests:
            msg = f"{where}: {method} {request_path} is listed more than once"
            raise CoverageError(msg)
        seen_requests.add((method, normalize(request_path)))
        sdk_only.append(
            SdkOnlyEntry(
                method=method,
                path=request_path,
                status=status,
                reason=_text(raw, "reason", where),
                ticket=_ticket(raw, where, required=status == UNDOCUMENTED),
                pattern=template_pattern(request_path),
            )
        )
    return Allowlist(operations=operations, sdk_only=sdk_only)


# --- comparison ---------------------------------------------------------------


@dataclass
class OperationResult:
    """Where one spec operation stands."""

    operation: Operation
    status: str
    tests: list[str]
    e2e: bool | None
    entry: OperationEntry | None


@dataclass(frozen=True)
class Problem:
    """One reason the report fails."""

    kind: str
    subject: str
    detail: str


@dataclass
class SdkOnlyResult:
    """Requests that match no spec operation: those one entry explains, or one unexplained path.

    `name` is the entry's request template, or the concrete request when no entry
    explains it.
    """

    entry: SdkOnlyEntry | None
    name: str
    requests: list[Request]


@dataclass
class Baseline:
    """How a spec differs from the snapshot it is checked against."""

    api: str
    source: str
    added: list[Operation]
    removed: list[Operation]
    restaged: list[tuple[Operation, str]]


@dataclass
class Report:
    """Everything the report says."""

    specs: dict[str, Spec]
    results: list[OperationResult]
    sdk_only: list[SdkOnlyResult]
    problems: list[Problem]
    offline_requests: int
    offline_tests: int
    e2e_records: list[Record]
    e2e_unmatched: list[str]
    baselines: list[Baseline]

    @property
    def exit_code(self) -> int:
        """1 when anything fails the report, else 0."""
        return 1 if self.problems else 0

    @property
    def e2e_ran(self) -> bool:
        """Whether any e2e test sent a request, which is what fills the e2e column."""
        return any(request.e2e for record in self.e2e_records for request in record.requests)


def _match(specs: dict[str, Spec], request: Request) -> list[Operation]:
    matched = (spec.match(request.method, request.path) for spec in specs.values())
    return [operation for operation in matched if operation is not None]


def _tests_by_operation(
    specs: dict[str, Spec], requests: Iterable[Request]
) -> tuple[dict[tuple[str, str, str], set[str]], list[Request]]:
    """Which tests sent each operation, and the requests that match no operation."""
    tests: dict[tuple[str, str, str], set[str]] = {}
    unmatched: list[Request] = []
    for request in requests:
        operations = _match(specs, request)
        if not operations:
            unmatched.append(request)
        for operation in operations:
            tests.setdefault(operation.key, set()).add(request.test)
    return tests, unmatched


def _sdk_only_entry(request: Request, entries: list[SdkOnlyEntry]) -> SdkOnlyEntry | None:
    candidates = [
        entry
        for entry in entries
        if entry.method == request.method and entry.pattern.match(request.path)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: (specificity(entry.path), entry.path))


def _sdk_only(
    unmatched: list[Request], entries: list[SdkOnlyEntry]
) -> tuple[list[SdkOnlyResult], list[Problem]]:
    explained: dict[SdkOnlyEntry, list[Request]] = {}
    unexplained: dict[str, list[Request]] = {}
    for request in unmatched:
        entry = _sdk_only_entry(request, entries)
        if entry is None:
            unexplained.setdefault(f"{request.method} {request.path}", []).append(request)
        else:
            explained.setdefault(entry, []).append(request)
    problems = [
        Problem(
            "sdk-only",
            f"{name} (sent by {requests[0].test})",
            "matches no spec operation and no sdk_only allowlist entry",
        )
        for name, requests in sorted(unexplained.items())
    ]
    problems += [
        Problem("stale", entry.name, "an sdk_only entry that no recorded request matches")
        for entry in entries
        if entry not in explained
    ]
    results = [
        SdkOnlyResult(None, name, requests) for name, requests in sorted(unexplained.items())
    ]
    results += sorted(
        (SdkOnlyResult(entry, entry.name, requests) for entry, requests in explained.items()),
        key=lambda result: result.name,
    )
    return results, problems


def _operation_results(
    specs: dict[str, Spec],
    covered: dict[tuple[str, str, str], set[str]],
    exercised: dict[tuple[str, str, str], set[str]] | None,
    allowlist: Allowlist,
) -> tuple[list[OperationResult], list[Problem]]:
    entries = {entry.key: entry for entry in allowlist.operations}
    results: list[OperationResult] = []
    problems: list[Problem] = []
    for spec in specs.values():
        for operation in spec.operations:
            tests = sorted(covered.get(operation.key, set()))
            entry = entries.pop(operation.key, None)
            e2e = None if exercised is None else operation.key in exercised
            if tests:
                status = COVERED
                if entry is not None:
                    problems.append(
                        Problem(
                            "stale",
                            _label(operation),
                            f"allowlisted as {entry.status} but covered now",
                        )
                    )
            elif entry is not None:
                status = entry.status
                if entry.stage != operation.stage:
                    problems.append(
                        Problem(
                            "changed",
                            _label(operation),
                            f"allowlisted as {entry.stage}, now {operation.stage} in the spec",
                        )
                    )
            else:
                status = MISSING
                if operation.stage == GA:
                    problems.append(
                        Problem("missing", _label(operation), "GA, neither covered nor allowlisted")
                    )
            results.append(OperationResult(operation, status, tests, e2e, entry))
    problems += [
        Problem("stale", f"{API_TITLES[entry.api]} {entry.name}", "allowlisted but not in the spec")
        for entry in entries.values()
    ]
    return results, problems


def _label(operation: Operation) -> str:
    return f"{API_TITLES[operation.api]} {operation.name}"


def _baseline(spec: Spec, baseline: Spec) -> Baseline:
    current = {operation.key: operation for operation in spec.operations}
    before = {operation.key: operation for operation in baseline.operations}
    return Baseline(
        api=spec.api,
        source=baseline.source,
        added=[op for key, op in current.items() if key not in before],
        removed=[op for key, op in before.items() if key not in current],
        restaged=[
            (op, before[key].stage)
            for key, op in current.items()
            if key in before and before[key].stage != op.stage
        ],
    )


def build_report(
    *,
    specs: dict[str, Spec],
    offline: list[Request],
    offline_tests: int,
    e2e_records: list[Record],
    allowlist: Allowlist,
    baselines: dict[str, Spec] | None = None,
) -> Report:
    """Compare the specs with the recorded requests and the allowlist.

    Args:
        specs: The spec of each API, by API name.
        offline: The requests the offline tests sent.
        offline_tests: How many tests the offline session ran.
        e2e_records: The records of the e2e sessions; empty when none ran.
        allowlist: The allowlist.
        baselines: Snapshots to list the specs' changes against, by API name.

    Returns:
        The report.
    """
    covered, unmatched = _tests_by_operation(specs, offline)
    exercised: dict[tuple[str, str, str], set[str]] | None = None
    e2e_unmatched: list[str] = []
    e2e_requests = [request for record in e2e_records for request in record.requests if request.e2e]
    if e2e_requests:
        successful = [r for r in e2e_requests if r.status in SUCCESS_STATUSES]
        exercised, missed = _tests_by_operation(specs, successful)
        e2e_unmatched = sorted({f"{request.method} {request.path}" for request in missed})
    results, problems = _operation_results(specs, covered, exercised, allowlist)
    sdk_only, sdk_only_problems = _sdk_only(unmatched, allowlist.sdk_only)
    return Report(
        specs=specs,
        results=results,
        sdk_only=sdk_only,
        problems=problems + sdk_only_problems,
        offline_requests=len(offline),
        offline_tests=offline_tests,
        e2e_records=e2e_records,
        e2e_unmatched=e2e_unmatched,
        baselines=[_baseline(specs[api], baseline) for api, baseline in (baselines or {}).items()],
    )


# --- rendering ----------------------------------------------------------------


def _cell(text: object) -> str:
    """Make external text safe inside a Markdown table cell or inline code."""
    return " ".join(str(text).split()).replace("|", "\\|").replace("`", "'")


def _e2e_cell(result: OperationResult) -> str:
    if result.e2e is None:
        return "not run"
    return "yes" if result.e2e else "no"


def _row(*cells: object) -> str:
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def _code(text: object) -> str:
    return f"`{_cell(text)}`"


def _counts_table(report: Report) -> list[str]:
    statuses = (COVERED, EXCLUDED, DEFERRED, UNTESTED, MISSING)
    out = [
        _row("API", "Stage", "Operations", *(s.capitalize() for s in statuses), "End to end"),
        _row(*["---"] * (len(statuses) + 4)),
    ]
    for api in APIS:
        for stage in STAGES:
            rows = [
                r for r in report.results if r.operation.api == api and r.operation.stage == stage
            ]
            if not rows:
                continue
            counts = [sum(1 for r in rows if r.status == status) for status in statuses]
            e2e = sum(1 for r in rows if r.e2e) if report.e2e_ran else "not run"
            out.append(_row(API_TITLES[api], stage, len(rows), *counts, e2e))
    return out


def _inputs(report: Report) -> list[str]:
    out = [f"- {API_TITLES[api]} spec: {report.specs[api].source}." for api in APIS]
    out.append(
        f"- Offline record: {report.offline_requests} requests from {report.offline_tests} tests."
    )
    if not report.e2e_records:
        out.append("- End to end: **not run** (no end-to-end record was given).")
    elif not report.e2e_ran:
        out.append("- End to end: **not run** (the end-to-end records hold no e2e request).")
    else:
        for record in report.e2e_records:
            e2e = sum(1 for request in record.requests if request.e2e)
            partial = (
                ""
                if record.exitstatus == 0
                else f" The session exited {record.exitstatus}, so the column may be incomplete."
            )
            out.append(f"- End to end: `{_cell(record.path.name)}`, {e2e} e2e requests.{partial}")
    return out


def _problems(report: Report) -> list[str]:
    titles = {
        "missing": "GA operations neither covered nor allowlisted",
        "changed": "Allowlisted operations whose stage changed",
        "stale": "Stale allowlist entries",
        "sdk-only": "SDK-only requests no allowlist entry explains",
    }
    out: list[str] = []
    for kind, title in titles.items():
        problems = [p for p in report.problems if p.kind == kind]
        if problems:
            out += [f"### {title}", ""]
            out += [f"- `{_cell(p.subject)}`: {_cell(p.detail)}" for p in problems]
            out.append("")
    out.append(
        "To resolve: add an offline test that sends the request, or triage the operation in "
        "`.github/scripts/api_coverage_allowlist.json` (one reason each, and the stage the "
        "spec gives it); refresh the snapshot under `.github/api-specs/` when the spec "
        'changed (see CONTRIBUTING.md, "API coverage report").'
    )
    out.append("")
    return out


def _details(summary: str, lines: list[str]) -> list[str]:
    return ["<details>", f"<summary>{summary}</summary>", "", *lines, "", "</details>", ""]


def _operation_tables(report: Report) -> list[str]:
    out: list[str] = []
    covered = [r for r in report.results if r.status == COVERED]
    out += _details(
        f"Covered operations ({len(covered)})",
        [
            _row("API", "Operation", "Stage", "Tests", "End to end"),
            _row(*["---"] * 5),
            *(
                _row(
                    API_TITLES[r.operation.api],
                    _code(r.operation.name),
                    r.operation.stage,
                    len(r.tests),
                    _e2e_cell(r),
                )
                for r in covered
            ),
        ],
    )
    missing = [r for r in report.results if r.status == MISSING]
    if missing:
        out += _details(
            f"Missing operations ({len(missing)})",
            [
                _row("API", "Operation", "Stage", "Summary"),
                _row(*["---"] * 4),
                *(
                    _row(
                        API_TITLES[r.operation.api],
                        _code(r.operation.name),
                        r.operation.stage,
                        _cell(r.operation.summary),
                    )
                    for r in missing
                ),
            ],
        )
    for status in ALLOWLIST_STATUSES:
        listed = [(r, r.entry) for r in report.results if r.status == status and r.entry]
        if listed:
            out += _details(
                f"{status.capitalize()} operations ({len(listed)})",
                [
                    _row("API", "Operation", "Stage", "Ticket", "Reason"),
                    _row(*["---"] * 5),
                    *(
                        _row(
                            API_TITLES[r.operation.api],
                            _code(r.operation.name),
                            r.operation.stage,
                            _cell(entry.ticket),
                            _cell(entry.reason),
                        )
                        for r, entry in listed
                    ),
                ],
            )
    return out


def _sdk_only_table(report: Report) -> list[str]:
    if not report.sdk_only:
        return []
    rows = [
        _row(
            _code(result.name),
            result.entry.status if result.entry else "**not allowlisted**",
            len(result.requests),
            _cell(result.entry.reason) if result.entry else "",
        )
        for result in report.sdk_only
    ]
    return _details(
        f"SDK-only requests ({len(report.sdk_only)})",
        [_row("Request", "Status", "Requests", "Reason"), _row(*["---"] * 4), *rows],
    )


def _baseline_section(report: Report) -> list[str]:
    out: list[str] = []
    for baseline in report.baselines:
        title = API_TITLES[baseline.api]
        changes = (
            [f"- added: `{_cell(op.name)}` ({op.stage})" for op in baseline.added]
            + [f"- removed: `{_cell(op.name)}` ({op.stage})" for op in baseline.removed]
            + [f"- `{_cell(op.name)}`: {before} -> {op.stage}" for op, before in baseline.restaged]
        )
        out += [f"### {title} spec changes since the snapshot", ""]
        out += [f"_Compared with {baseline.source}._", ""]
        out += changes or ["None."]
        out.append("")
    return out


def render(report: Report) -> str:
    """Render the Markdown report, ending with a newline."""
    out = ["## API coverage", ""]
    if report.exit_code == 0:
        out.append(
            ":white_check_mark: **Every GA operation is covered or allowlisted**, and the "
            "allowlist is current."
        )
    else:
        out.append(f":x: **The API coverage report fails: {len(report.problems)} problem(s).**")
    out += ["", *_inputs(report), "", *_counts_table(report), ""]
    out += [
        (
            "_Covered: an offline test sent the request. Request and response shapes are "
            "checked by the weekly Schema Drift workflow, not here._"
        ),
        "",
    ]
    if report.problems:
        out += _problems(report)
    out += _baseline_section(report)
    out += _operation_tables(report)
    out += _sdk_only_table(report)
    if report.e2e_unmatched:
        out += _details(
            f"End-to-end requests that match no operation ({len(report.e2e_unmatched)})",
            [f"- `{_cell(name)}`" for name in report.e2e_unmatched],
        )
    return "\n".join(out)


def as_json(report: Report) -> dict[str, Any]:
    """The full result, for the JSON artifact."""
    return {
        "result": "pass" if report.exit_code == 0 else "fail",
        "exit_code": report.exit_code,
        "specs": {api: spec.source for api, spec in report.specs.items()},
        "offline": {"requests": report.offline_requests, "tests": report.offline_tests},
        "e2e": (
            [
                {"record": str(r.path), "exitstatus": r.exitstatus, "tests": r.tests}
                for r in report.e2e_records
            ]
            if report.e2e_ran
            else "not run"
        ),
        "problems": [vars(problem) for problem in report.problems],
        "operations": [
            {
                "api": r.operation.api,
                "operation": r.operation.name,
                "stage": r.operation.stage,
                "tags": list(r.operation.tags),
                "summary": r.operation.summary,
                "status": r.status,
                "tests": r.tests[:TESTS_PER_OPERATION],
                "test_count": len(r.tests),
                "e2e": "not run" if r.e2e is None else r.e2e,
                "ticket": r.entry.ticket if r.entry else "",
                "reason": r.entry.reason if r.entry else "",
            }
            for r in report.results
        ],
        "sdk_only": [
            {
                "request": r.name,
                "status": r.entry.status if r.entry else "not allowlisted",
                "requests": len(r.requests),
                "tests": sorted({request.test for request in r.requests})[:TESTS_PER_OPERATION],
                "reason": r.entry.reason if r.entry else "",
            }
            for r in report.sdk_only
        ],
        "e2e_unmatched": report.e2e_unmatched,
        "baselines": [
            {
                "api": b.api,
                "added": [op.name for op in b.added],
                "removed": [op.name for op in b.removed],
                "restaged": [
                    {"operation": op.name, "was": was, "now": op.stage} for op, was in b.restaged
                ],
            }
            for b in report.baselines
        ],
    }


def _did_not_run(reason: str) -> str:
    first_line = (reason.splitlines() or [""])[0]
    return (
        "## API coverage\n\n"
        ":warning: **The report did not run**, so this is not a clean result.\n\n"
        f"`{_cell(first_line)}`\n"
    )


# --- command line -------------------------------------------------------------


def _named_values(values: list[str] | None, option: str) -> dict[str, str]:
    named: dict[str, str] = {}
    for value in values or []:
        name, sep, rest = value.partition("=")
        if not sep or name not in APIS or not rest:
            msg = f"{option} takes NAME=VALUE with NAME one of {', '.join(APIS)}, not {value!r}"
            raise CoverageError(msg)
        if name in named:
            msg = f"{option} {name} is given more than once"
            raise CoverageError(msg)
        named[name] = rest
    return named


def _minimums(values: list[str] | None) -> dict[str, int]:
    minimums = dict(DEFAULT_MIN_OPERATIONS)
    for name, text in _named_values(values, "--min-operations").items():
        if not text.isdigit():
            msg = f"--min-operations {name} needs a whole number, not {text!r}"
            raise CoverageError(msg)
        minimums[name] = int(text)
    return minimums


def run(args: argparse.Namespace) -> Report:
    """Read every input and build the report.

    Raises:
        CoverageError: If any input fails its checks (exit 2).
    """
    spec_paths = _named_values(args.spec, "--spec")
    if set(spec_paths) != set(APIS):
        msg = f"--spec is needed for each of {', '.join(APIS)}"
        raise CoverageError(msg)
    minimums = _minimums(args.min_operations)
    allowlist = load_allowlist(Path(args.allowlist))
    specs = {api: load_spec(api, Path(spec_paths[api]), minimums[api]) for api in APIS}
    baselines = {
        api: load_spec(api, Path(path), 1)
        for api, path in _named_values(args.baseline, "--baseline").items()
    }
    record = load_record(Path(args.record))
    offline = check_offline_record(record, args.min_records)
    e2e_records = [load_record(Path(path)) for path in args.e2e_record or []]
    return build_report(
        specs=specs,
        offline=offline,
        offline_tests=record.tests,
        e2e_records=e2e_records,
        allowlist=allowlist,
        baselines=baselines,
    )


def report_command(args: argparse.Namespace) -> int:
    """Run the report and write its outputs; return the exit status (0, 1 or 2)."""
    try:
        report = run(args)
    except CoverageError as exc:
        reason = str(exc)
        print(f"API coverage report did not run: {reason}", file=sys.stderr)
    # Any other error is also a run that did not finish, not a coverage failure: exit 1
    # would read as a failing report with nothing listed.
    except Exception as exc:  # noqa: BLE001 - mapped to exit 2 with its traceback on stderr
        traceback.print_exc()
        reason = f"{type(exc).__name__}: {exc}"
    else:
        return _write_report(args, report)
    _emit(_did_not_run(reason), args.summary)
    _write_json(args.json, {"result": "did-not-run", "exit_code": 2, "reason": reason})
    return 2


def _write_report(args: argparse.Namespace, report: Report) -> int:
    _emit(render(report), args.summary)
    _write_json(args.json, as_json(report))
    if args.github_output:
        kinds = ("missing", "stale", "changed", "sdk-only")
        counts = {kind: sum(1 for p in report.problems if p.kind == kind) for kind in kinds}
        with Path(args.github_output).open("a", encoding="utf-8") as handle:
            handle.write(
                "".join(f"{kind.replace('-', '_')}={count}\n" for kind, count in counts.items())
            )
    for problem in report.problems:
        print(f"{problem.kind}: {problem.subject}: {problem.detail}", file=sys.stderr)
    return report.exit_code


def inventory(document: Any, api: str, label: str) -> dict[str, Any]:  # noqa: ANN401
    """The part of a spec the report reads: each operation's id, summary, tags and stage.

    Raises:
        CoverageError: If the document has no operations.
    """
    paths: dict[str, dict[str, Any]] = {}
    for operation in operations_of(document, api, label):
        source = document["paths"][operation.path][operation.method.lower()]
        kept = {"operationId": source.get("operationId"), "summary": source.get("summary")}
        kept["tags"] = source.get("tags") or []
        if source.get("deprecated") is True:
            kept["deprecated"] = True
        paths.setdefault(operation.path, {})[operation.method.lower()] = kept
    if not paths:
        msg = f"{label} has no operations"
        raise CoverageError(msg)
    info = document.get("info") or {}
    return {
        "openapi": document.get("openapi"),
        "info": {"title": info.get("title"), "version": info.get("version")},
        "paths": paths,
    }


def snapshot_command(args: argparse.Namespace) -> int:
    """Write the operation inventory of a spec, and its source next to it."""
    try:
        label = f"the {API_TITLES[args.api]} spec"
        document = read_json(Path(args.spec), label)
        snapshot = inventory(document, args.api, f"{label} at {args.spec}")
    except CoverageError as exc:
        print(f"could not write the snapshot: {exc}", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    operations = sum(len(item) for item in snapshot["paths"].values())
    fetched = args.fetched or dt.datetime.now(dt.timezone.utc).date().isoformat()
    source = {"source": args.source, "fetched": fetched, "operations": operations}
    _write(out_dir / f"{args.api}.json", snapshot)
    _write(out_dir / f"{args.api}.source.json", source)
    print(f"wrote {operations} {API_TITLES[args.api]} operations to {out_dir / args.api}.json")
    return 0


def _write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_json(target: str | None, document: object) -> None:
    if target:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        _write(Path(target), document)


def _emit(report: str, summary: str | None) -> None:
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    else:
        print(report)


def parser() -> argparse.ArgumentParser:
    """The command line: `report` and `snapshot`."""
    root = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    commands = root.add_subparsers(dest="command", required=True)

    report = commands.add_parser("report", help="compare the specs with a request record")
    report.add_argument(
        "--spec",
        action="append",
        metavar="NAME=PATH",
        help=f"the spec of each API ({', '.join(APIS)}): an OpenAPI document or a snapshot",
    )
    report.add_argument("--allowlist", required=True, help="the allowlist (JSON)")
    report.add_argument("--record", required=True, help="the offline tests' request record")
    report.add_argument(
        "--e2e-record", action="append", metavar="PATH", help="an e2e run's request record"
    )
    report.add_argument(
        "--baseline",
        action="append",
        metavar="NAME=PATH",
        help="a snapshot to list the spec's changes against",
    )
    report.add_argument(
        "--min-records",
        type=int,
        default=DEFAULT_MIN_RECORDS,
        help="fewest offline requests the record must hold (default: %(default)s)",
    )
    report.add_argument(
        "--min-operations",
        action="append",
        metavar="NAME=N",
        help="fewest operations a spec must list (defaults: "
        + ", ".join(f"{api}={n}" for api, n in DEFAULT_MIN_OPERATIONS.items())
        + ")",
    )
    report.add_argument("--summary", help="append the Markdown report here instead of stdout")
    report.add_argument("--json", help="write the full result here as JSON")
    report.add_argument(
        "--github-output", help="append missing=, stale=, changed= and sdk_only= counts here"
    )
    report.set_defaults(handler=report_command)

    snapshot = commands.add_parser("snapshot", help="write a spec's operation inventory")
    snapshot.add_argument("api", choices=APIS)
    snapshot.add_argument("spec", help="the downloaded OpenAPI document")
    snapshot.add_argument("--source", required=True, help="where the document came from")
    snapshot.add_argument("--fetched", help="when it was fetched (default: today, UTC)")
    snapshot.add_argument(
        "--out-dir", default=".github/api-specs", help="where to write (default: %(default)s)"
    )
    snapshot.set_defaults(handler=snapshot_command)
    return root


def main(argv: list[str] | None = None) -> int:
    """Run a subcommand; return its exit status.

    Bad arguments exit 2 through argparse, and so does an error while writing the
    outputs: neither is a coverage result.
    """
    args = parser().parse_args(argv)
    try:
        status: int = args.handler(args)
    except Exception:  # noqa: BLE001 - mapped to exit 2 with its traceback on stderr
        traceback.print_exc()
        return 2
    return status


if __name__ == "__main__":
    sys.exit(main())
