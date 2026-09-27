#!/usr/bin/env python3
"""Find what a permit 2.x -> 3.0.0 upgrade touches in a project.

Read-only and standard library only, so it runs on Python 3.8 and later, before
the project itself has moved. It walks the project's Python files with `ast`,
plus its dependency, CI and type-checker configuration, and prints one line per
affected site:

    path:line: ID SAFE|NEEDS-REVIEW message

ID is a change ID from references/changes.md. SAFE marks an edit that can be
applied as described; NEEDS-REVIEW marks a site where the right edit depends on
something static analysis cannot see.

Usage:
    python scan.py [PROJECT_DIR] [--json]

Exit status: 0 whatever is found, 2 on a usage error.
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, NamedTuple, Optional, Set, Tuple, Union

SAFE = "SAFE"
REVIEW = "NEEDS-REVIEW"

# What a name holds, when it is traced to a permit client.
ASYNC = "async"
SYNC = "sync"
EITHER = "either"  # a permit client: the async one in one place, the blocking one in another
MAYBE = "maybe"  # a permit client in one place, something else in another
CLIENTS = (ASYNC, SYNC, EITHER)

TITLES = {
    "P1": "The permit requirement",
    "C1": "Python 3.10 or later",
    "C2": "httpx is no longer installed with permit",
    "C3": "Higher dependency floors",
    "T1": "permit ships type information",
    "T2": "pydantic 2 methods on SDK models",
    "A1": "resource_relations.list() returns a page",
    "A2": "Three permit.sync.Permit methods are synchronous",
    "A3": "Removed symbols",
    "A4": "Audit-log models accept what the API returns",
    "A5": "Relationship-tuple and API-key models accept what the API returns",
    "A6": "Other names no longer importable",
    "W1": "An explicit None is sent as null",
    "W5": "Authorization: Bearer",
    "D1": "pydantic 1 support is deprecated",
    "D2": "The flat permit.api methods are deprecated",
}

# Deprecated flat method -> (replacement, relative to the client; keyword renames).
# A None rename map means the three arguments become one assignment argument.
DEPRECATED_METHODS: Dict[str, Tuple[str, Optional[Dict[str, str]]]] = {
    "get_user": ("api.users.get", {}),
    "get_role": ("api.roles.get", {}),
    "get_tenant": ("api.tenants.get", {}),
    "get_assigned_roles": ("api.users.get_assigned_roles", {"user_key": "user", "tenant_key": "tenant"}),
    "get_resource": ("api.resources.get", {}),
    "list_roles": ("api.roles.list", {}),
    "sync_user": ("api.users.sync", {}),
    "delete_user": ("api.users.delete", {}),
    "list_tenants": ("api.tenants.list", {}),
    "create_tenant": ("api.tenants.create", {"tenant": "tenant_data"}),
    "update_tenant": ("api.tenants.update", {"tenant": "tenant_data"}),
    "delete_tenant": ("api.tenants.delete", {}),
    "create_role": ("api.roles.create", {"role": "role_data"}),
    "update_role": ("api.roles.update", {"role": "role_data"}),
    "assign_role": ("api.users.assign_role", None),
    "unassign_role": ("api.users.unassign_role", None),
    "delete_role": ("api.roles.delete", {}),
    "create_resource": ("api.resources.create", {"resource": "resource_data"}),
    "update_resource": ("api.resources.update", {"resource": "resource_data"}),
    "delete_resource": ("api.resources.delete", {}),
    "elements_login_as": ("elements.login_as", {}),
}
ASSIGNMENT_KEYS = {"user_key": "user", "role_key": "role", "tenant_key": "tenant"}

NOW_SYNC_METHODS = {"authorized_users", "get_user_permissions", "filter_objects"}
PAGE_FIELDS = {"data", "total_count", "page_count"}
COROUTINE_RUNNERS = {"run", "run_until_complete", "gather", "create_task", "ensure_future", "wait_for"}
# Modules whose import aliases the scan follows: permit, and asyncio for its runners.
TRACED_MODULES = {"permit", "asyncio"}

ASYNC_CLIENTS = {"permit.Permit", "permit.permit.Permit"}
SYNC_CLIENTS = {"permit.sync.Permit"}
MODEL_MODULES = {"permit", "permit.api.models"}

_TYPEVAR_FIX = "define your own TypeVar"
_TYPING_FIX = "import it from typing"
_PYDANTIC_FIX = "import it from pydantic.v1, which permit 3's pydantic floors always provide"
_VERSION_FIX = "import PYDANTIC_VERSION from permit.utils.pydantic_version"
REMOVED: Dict[Tuple[str, str], Tuple[str, str, str]] = {
    ("permit.api.context", "ApiKeyLevel"): ("A3", SAFE, "use ApiKeyAccessLevel, which has the same members"),
    ("permit.enforcement.interfaces", "JWT"): ("A3", SAFE, "JWT was an alias of str; use str"),
    ("permit.utils.context", "ContextTransform"): (
        "A3",
        REVIEW,
        "removed with ContextStore.register_transform(); use Callable[[Dict[str, Any]], Dict[str, Any]] if you "
        "still need the type",
    ),
    ("permit.api.elements", "LoginAsErrorMessages"): (
        "A3",
        REVIEW,
        "removed; define the messages you compare against in your own code",
    ),
    ("permit.enforcement.interfaces", "OpaResult"): (
        "A3",
        REVIEW,
        "removed; nothing in the SDK returned it. Define an equivalent model if you need one",
    ),
    ("permit", "PYDANTIC_VERSION"): ("A6", SAFE, _VERSION_FIX),
    ("permit.api.models", "PYDANTIC_VERSION"): ("A6", SAFE, _VERSION_FIX),
    ("permit.pdp_api.base", "PYDANTIC_VERSION"): ("A6", SAFE, _VERSION_FIX),
    ("permit.enforcement.enforcer", "set_if_not_none"): ("A6", SAFE, "removed; copy the three-line helper"),
    ("permit.pdp_api.base", "T"): ("A6", SAFE, _TYPEVAR_FIX),
    ("permit.pdp_api.base", "TModel"): ("A6", SAFE, _TYPEVAR_FIX),
    ("permit.pdp_api.base", "TData"): ("A6", SAFE, _TYPEVAR_FIX),
    ("permit.pdp_api.base", "BaseModel"): ("A6", SAFE, _PYDANTIC_FIX),
    ("permit.pdp_api.base", "Extra"): ("A6", SAFE, _PYDANTIC_FIX),
    ("permit.pdp_api.base", "Field"): ("A6", SAFE, _PYDANTIC_FIX),
    ("permit.pdp_api.base", "Callable"): ("A6", SAFE, _TYPING_FIX),
    ("permit.pdp_api.base", "TypeVar"): ("A6", SAFE, _TYPING_FIX),
    ("permit.utils.context", "Callable"): ("A6", SAFE, _TYPING_FIX),
    ("permit.utils.context", "List"): ("A6", SAFE, _TYPING_FIX),
    ("permit.api.resource_relations", "List"): ("A6", SAFE, _TYPING_FIX),
    ("permit.api.elements", "Enum"): ("A6", SAFE, "import it from enum"),
    ("permit.api.deprecated", "RoleAssignmentsApi"): ("A6", SAFE, "import it from permit.api.role_assignments"),
    ("permit.utils.sync", "iscoroutinefunction"): ("A6", SAFE, "import it from inspect"),
}

AUDIT_LOG_MODELS = {"AuditLogModel", "DetailedAuditLogModel"}
TUPLE_MODELS = {"RelationshipTupleRead", "RelationshipTupleDetailedRead"}
TUPLE_OPTIONAL_FIELDS = {"object_id", "subject_details", "relation_details", "object_details", "tenant_details"}
NEW_ENUM_MEMBERS = {"Engine": ("A4", "Engine.GENERIC"), "APIKeyOwnerType": ("A5", "APIKeyOwnerType.nats_pdp_config")}

# pydantic 2 method -> (pydantic 1 method, keywords the two share).
V2_METHODS: Dict[str, Tuple[str, Set[str]]] = {
    "model_dump": (
        "dict",
        {"include", "exclude", "by_alias", "exclude_unset", "exclude_defaults", "exclude_none"},
    ),
    "model_dump_json": (
        "json",
        {"include", "exclude", "by_alias", "exclude_unset", "exclude_defaults", "exclude_none", "indent"},
    ),
    "model_validate": ("parse_obj", set()),
    "model_validate_json": ("parse_raw", set()),
    "model_copy": ("copy", {"update", "deep"}),
    "model_json_schema": ("schema", {"by_alias", "ref_template"}),
}
V2_ATTRIBUTES = {"model_fields_set": "__fields_set__", "model_fields": "__fields__", "model_config": "__config__"}
REQUEST_MODEL_SUFFIXES = ("Create", "Update", "Remove", "Delete", "Replace")

# Packages permit 2.x installed and 3.0.0 does not: httpx and zipp, which it declared, and the
# packages only httpx brought in. idna and typing-extensions still come with permit 3.
TRANSITIVE_PACKAGES = {
    "httpx": "permit 2.x declared it",
    "zipp": "permit 2.x declared it",
    "httpcore": "permit 2.x installed it through httpx",
    "h11": "permit 2.x installed it through httpx",
    "anyio": "permit 2.x installed it through httpx",
    "certifi": "permit 2.x installed it through httpx",
    "sniffio": "permit 2.x installed it through httpx and anyio releases that need it",
    "exceptiongroup": "permit 2.x installed it through anyio on Python 3.10",
}

# mypy and pyright codes for "this package has no type information".
IMPORT_IGNORE_CODES = {
    "import",
    "import-untyped",
    "import-not-found",
    "reportMissingTypeStubs",
    "reportMissingImports",
    "reportMissingModuleSource",
}

Version = Tuple[int, ...]
Bound = Tuple[str, Version]

# Allowed version ranges in permit 3.0.0, as [low, high) pairs; None is open.
FLOORS: Dict[str, List[Tuple[Optional[Version], Optional[Version]]]] = {
    "aiohttp": [((3, 14, 3), (4,))],
    "typing-extensions": [((4, 14, 0), (5,))],
    "loguru": [((0, 7, 3), (1,))],
    "pydantic": [((1, 10, 18), (2,)), ((2, 4, 2), None)],
}
FLOOR_TEXT = {
    "aiohttp": "aiohttp>=3.14.3,<4",
    "typing-extensions": "typing-extensions>=4.14.0,<5",
    "loguru": "loguru>=0.7.3,<1",
    "pydantic": "pydantic>=1.10.18,<2 or >=2.4.2 (>=2.8.0 on Python 3.13; >=1.10.25,<2 or >=2.13 on 3.14)",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "site-packages",
    "dist-packages",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    ".tox",
    ".nox",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
LOCK_FILES = {"poetry.lock", "uv.lock", "pdm.lock", "Pipfile.lock"}
CI_FILE_NAMES = {".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml"}


class Finding(NamedTuple):
    path: str
    line: int
    change: str
    safety: str
    message: str


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# ---------------------------------------------------------------------------
# Version specifiers
# ---------------------------------------------------------------------------


def parse_version(text: str) -> Optional[Version]:
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", text)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _padded(left: Version, right: Version) -> Tuple[Version, Version]:
    length = max(len(left), len(right))
    return left + (0,) * (length - len(left)), right + (0,) * (length - len(right))


def compare(left: Version, right: Version) -> int:
    left, right = _padded(left, right)
    return (left > right) - (left < right)


def bump(version: Version, index: int) -> Version:
    index = max(0, min(index, len(version) - 1))
    return (*version[:index], version[index] + 1)


_CLAUSE_RE = re.compile(r"^(===|==|!=|~=|>=|<=|>|<|\^|~)?\s*v?([0-9][0-9A-Za-z.*+!-]*)$")


def clause_bounds(clause: str) -> Optional[List[Bound]]:
    """Turn one specifier clause into bounds. None means the clause is not understood."""
    clause = clause.strip()
    if clause in ("", "*"):
        return []
    match = _CLAUSE_RE.match(clause)
    if match is None:
        return None
    operator = match.group(1) or "=="
    raw = match.group(2)
    version = parse_version(raw)
    if version is None:
        return None
    if operator == "!=":
        return []
    if operator in ("==", "===") and raw.endswith(".*"):
        return [(">=", version), ("<", bump(version, len(version) - 1))]
    if operator in ("==", "==="):
        return [("==", version)]
    if operator == "~=":
        if len(version) < 2:
            return None
        return [(">=", version), ("<", bump(version, len(version) - 2))]
    if operator == "^":
        nonzero = [index for index, part in enumerate(version) if part != 0]
        return [(">=", version), ("<", bump(version, nonzero[0] if nonzero else len(version) - 1))]
    if operator == "~":
        return [(">=", version), ("<", bump(version, 1 if len(version) >= 2 else 0))]
    return [(operator, version)]


def parse_spec(spec: str) -> Optional[List[List[Bound]]]:
    """Parse a PEP 440 or Poetry specifier into alternatives of bounds. None if not understood."""
    alternatives: List[List[Bound]] = []
    for alternative in spec.split("||"):
        bounds: List[Bound] = []
        for part in alternative.split(","):
            for clause in re.split(r"\s+(?=[<>=!~^])", part.strip()):
                parsed = clause_bounds(clause)
                if parsed is None:
                    return None
                bounds.extend(parsed)
        alternatives.append(bounds)
    return alternatives


def _intersects(bounds: List[Bound], low: Optional[Version], high: Optional[Version]) -> bool:
    lower: Optional[Tuple[Version, bool]] = (low, True) if low is not None else None
    upper: Optional[Tuple[Version, bool]] = (high, False) if high is not None else None
    for operator, version in bounds:
        if operator in (">=", ">", "=="):
            inclusive = operator != ">"
            if lower is None or compare(version, lower[0]) > 0:
                lower = (version, inclusive)
            elif compare(version, lower[0]) == 0:
                lower = (version, lower[1] and inclusive)
        if operator in ("<=", "<", "=="):
            inclusive = operator != "<"
            if upper is None or compare(version, upper[0]) < 0:
                upper = (version, inclusive)
            elif compare(version, upper[0]) == 0:
                upper = (version, upper[1] and inclusive)
    if lower is None or upper is None:
        return True
    order = compare(lower[0], upper[0])
    return order < 0 or (order == 0 and lower[1] and upper[1])


def intersects(alternatives: List[List[Bound]], low: Optional[Version], high: Optional[Version]) -> bool:
    """Whether some version in [low, high) satisfies the parsed specifier."""
    return any(_intersects(bounds, low, high) for bounds in alternatives)


def python_below_310(spec: str) -> bool:
    alternatives = parse_spec(spec)
    return alternatives is not None and intersects(alternatives, None, (3, 10))


def minors_below_310(text: str) -> List[str]:
    """Python versions like 3.9 or 3.9.18 in text that are older than 3.10."""
    found = []
    for match in re.finditer(r"(?<![\w.])3\.(\d+)(?:\.\d+)?(?![\w.])", text):
        if int(match.group(1)) < 10:
            found.append(match.group(0))
    return found


# ---------------------------------------------------------------------------
# Dependency and configuration files
# ---------------------------------------------------------------------------


class Requirement(NamedTuple):
    path: str
    line: int
    name: str
    spec: str
    text: str


_REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


def split_requirement(text: str) -> Optional[Tuple[str, str]]:
    """Split a PEP 508 string into (normalized name, specifier). Markers are dropped."""
    text = text.split(";", 1)[0].strip()
    match = _REQUIREMENT_RE.match(text)
    if match is None:
        return None
    rest = match.group(3).strip()
    if rest.startswith("@"):
        return normalize_name(match.group(1)), "@"
    return normalize_name(match.group(1)), rest.strip("()").strip()


class ProjectFacts:
    """What the dependency and configuration files say, gathered before the code is scanned."""

    def __init__(self) -> None:
        self.requirements: List[Requirement] = []
        self.locked_permit: List[Tuple[str, int, str]] = []
        self.python_pins: List[Tuple[str, int, str]] = []
        self.pytest_error_filters: List[Tuple[str, int]] = []
        self.pydantic1_filter_present = False
        self.findings: List[Finding] = []

    def add_requirement(self, path: str, line: int, text: str) -> None:
        parsed = split_requirement(text)
        if parsed is not None:
            self.requirements.append(Requirement(path, line, parsed[0], parsed[1], text.strip()))

    def add_python_pin(self, path: str, line: int, text: str, *, below: bool) -> None:
        self.python_pins.append((path, line, text.strip()))
        if below:
            self.findings.append(
                Finding(
                    path,
                    line,
                    "C1",
                    REVIEW,
                    f"`{text.strip()}` allows or targets Python below 3.10; permit 3 needs 3.10+",
                )
            )

    def declared(self) -> Set[str]:
        return {requirement.name for requirement in self.requirements}

    def pins_pydantic1(self) -> bool:
        for requirement in self.requirements:
            if requirement.name != "pydantic":
                continue
            alternatives = parse_spec(requirement.spec)
            if alternatives is not None and not intersects(alternatives, (2,), None):
                return True
        return False


_COMPILED_RE = re.compile(r"#\s*(?:This file (?:is|was) autogenerated by|via\b)")


def requirement_lines(lines: List[str]) -> Iterator[Tuple[int, str]]:
    for number, raw in enumerate(lines, 1):
        text = re.split(r"\s#", raw, maxsplit=1)[0].strip()
        if text and not text.startswith(("#", "-")):
            yield number, text.rstrip("\\").strip()


def scan_requirements_txt(facts: ProjectFacts, rel: str, lines: List[str]) -> None:
    if any(_COMPILED_RE.search(line) for line in lines):
        # pip-compile or `uv pip compile` output is a lock: its pins follow from the requirements it
        # was compiled from, and `httpx==...  # via permit` is not the project declaring httpx.
        for number, text in requirement_lines(lines):
            parsed = split_requirement(text)
            pinned = re.match(r"^===?\s*([^\s,;]+)$", parsed[1]) if parsed and parsed[0] == "permit" else None
            if pinned:
                _locked_permit(facts, rel, number, pinned.group(1), compiled=True)
        return
    for number, text in requirement_lines(lines):
        facts.add_requirement(rel, number, text)


_TABLE_RE = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$")
_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_.\"'-]+)\s*=\s*(.*)$")
_QUOTED_RE = re.compile(r"\"([^\"]*)\"|'([^']*)'")


def _quoted(text: str) -> List[str]:
    return [double if double else single for double, single in _QUOTED_RE.findall(text)]


def _unquoted(text: str) -> str:
    return _QUOTED_RE.sub("", text)


def _requirement_key(table: str, key: str) -> bool:
    if table == "project":
        return key == "dependencies"
    if table in ("project.optional-dependencies", "dependency-groups"):
        return True
    if table == "tool.uv":
        return key in ("dev-dependencies", "constraint-dependencies", "override-dependencies")
    return table.startswith("tool.pdm") and "dependencies" in (table + key)


def _poetry_table(table: str) -> bool:
    return table in ("tool.poetry.dependencies", "tool.poetry.dev-dependencies") or bool(
        re.match(r"tool\.poetry\.group\.[^.]+\.dependencies$", table)
    )


def _table_value_spec(value: str) -> Optional[str]:
    """The version spec of a Poetry or Pipfile entry: "spec" or {version = "spec", ...}."""
    value = value.strip()
    if value.startswith("{"):
        match = re.search(r"version\s*=\s*[\"']([^\"']*)[\"']", value)
        return match.group(1) if match else None
    quoted = _quoted(value)
    return quoted[0] if quoted else None


def scan_toml(facts: ProjectFacts, rel: str, lines: List[str], *, pipfile: bool) -> None:
    """Line-based reading of pyproject.toml and Pipfile: no TOML parser in 3.8's stdlib."""
    table = ""
    array_key: Optional[str] = None
    block: List[Tuple[int, str]] = []

    def close_block() -> None:
        if table == "tool.mypy.overrides":
            scan_mypy_override_block(facts, rel, block)

    for number, raw in enumerate(lines, 1):
        text = raw if raw.strip().startswith(('"', "'")) else raw.split("#", 1)[0]
        header = _TABLE_RE.match(raw)
        if header and array_key is None:
            close_block()
            table = header.group(1).strip().replace('"', "").replace("'", "")
            block = []
            continue
        block.append((number, raw))
        key: Optional[str] = None
        value = text
        if array_key is None:
            key_match = _KEY_RE.match(text)
            if key_match:
                key = key_match.group(1).strip("\"'")
                value = key_match.group(2)
            if key is not None and value.strip().startswith("[") and "]" not in _unquoted(value):
                array_key = key
        current_key = array_key if array_key is not None else key

        if pipfile and table in ("packages", "dev-packages") and key is not None and array_key is None:
            spec = _table_value_spec(value)
            if spec is not None:
                facts.add_requirement(rel, number, f"{key} {'' if spec == '*' else spec}")
        elif not pipfile and _poetry_table(table) and key is not None and array_key is None:
            spec = _table_value_spec(value)
            if key == "python" and spec is not None:
                facts.add_python_pin(rel, number, f'python = "{spec}"', below=python_below_310(spec))
            elif spec is not None:
                facts.add_requirement(rel, number, f"{key} {'' if spec == '*' else spec}")
        elif current_key is not None and _requirement_key(table, current_key):
            for requirement in _quoted(value):
                facts.add_requirement(rel, number, requirement)

        if table == "project" and key == "requires-python":
            for spec in _quoted(value):
                facts.add_python_pin(rel, number, f'requires-python = "{spec}"', below=python_below_310(spec))
        if table == "project" and current_key == "classifiers":
            scan_classifiers(facts, rel, number, text)
        if (pipfile and table == "requires") or table in ("tool.mypy", "tool.pyright"):
            scan_version_setting(facts, rel, number, raw)
        if table == "tool.pytest.ini_options" and current_key in ("filterwarnings", "addopts"):
            scan_pytest_setting(facts, rel, number, text)

        if array_key is not None and "]" in _unquoted(text if key is None else value):
            array_key = None
    close_block()


def scan_classifiers(facts: ProjectFacts, rel: str, number: int, text: str) -> None:
    match = re.search(r"Programming Language :: Python :: (3\.\d+)", text)
    if match:
        version = match.group(1)
        facts.add_python_pin(rel, number, version, below=bool(minors_below_310(version)))


def scan_version_setting(facts: ProjectFacts, rel: str, number: int, raw: str) -> None:
    """python_version (mypy, Pipfile), pythonVersion (pyright) and python_full_version."""
    match = re.match(
        r"^\s*[\"']?(python_version|pythonVersion|python_full_version)[\"']?\s*[:=]\s*[\"']?(\d+\.\d+)", raw
    )
    if match:
        facts.add_python_pin(rel, number, raw.strip().rstrip(","), below=bool(minors_below_310(match.group(2))))


_ERROR_FILTER_RE = re.compile(r"(?:^|[\s\"',\[=])(?:-W\s*)?error(?:::(?:DeprecationWarning|Warning))?(?=$|[\s\"',\]])")


# A warning filter for permit 2.x's deprecation text, "use permit.api.users.get() instead". Filters
# match from the start of the message, which in permit 3 is "permit.api.get_user() is deprecated".
OLD_D2_TEXT_RE = re.compile(r"(?:^|:)\s*use permit\\?\.(?:api|elements)\b")
OLD_D2_FILTER = (
    'this warning filter matches permit 2.x\'s deprecation text ("use permit.api....() instead"). permit 3 '
    'warns "permit.api.<method>() is deprecated and will be removed in permit 4.0; ...", which it does not '
    "match: delete it once the calls are migrated, or match `permit\\.api\\.\\w+\\(\\) is deprecated` instead"
)


def scan_pytest_setting(facts: ProjectFacts, rel: str, number: int, text: str) -> None:
    if "Support for pydantic 1" in text:
        facts.pydantic1_filter_present = True
    if _ERROR_FILTER_RE.search(text):
        facts.pytest_error_filters.append((rel, number))
    if OLD_D2_TEXT_RE.search(text):
        facts.findings.append(Finding(rel, number, "D2", REVIEW, OLD_D2_FILTER))


def scan_mypy_override_block(facts: ProjectFacts, rel: str, block: List[Tuple[int, str]]) -> None:
    permit_lines = [number for number, raw in block if re.search(r"[\"']permit(\.\*)?[\"']", raw)]
    hides = any(
        re.match(r"^\s*(ignore_missing_imports\s*=\s*true|follow_imports\s*=\s*[\"']skip[\"'])", raw)
        for _, raw in block
    )
    if permit_lines and hides:
        facts.findings.append(
            Finding(rel, permit_lines[0], "T1", SAFE, "permit ships py.typed now: remove permit from this override")
        )


def scan_ini(facts: ProjectFacts, rel: str, lines: List[str]) -> None:
    """setup.cfg, tox.ini, mypy.ini and pytest.ini."""
    section = ""
    section_line = 0
    key: Optional[str] = None
    hides_permit = False
    name = Path(rel).name

    def close_section() -> None:
        if hides_permit:
            facts.findings.append(
                Finding(rel, section_line, "T1", SAFE, "permit ships py.typed now: remove permit from this section")
            )

    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        header = re.match(r"^\[([^\]]+)\]", stripped)
        if header:
            close_section()
            section = header.group(1).strip()
            section_line = number
            key = None
            hides_permit = False
            continue
        continuation = raw[:1] in (" ", "\t")
        if not continuation:
            key_match = re.match(r"^([A-Za-z0-9_.-]+)\s*[=:]\s*(.*)$", stripped)
            key = key_match.group(1) if key_match else None
            value = key_match.group(2) if key_match else ""
        else:
            value = stripped

        modules = (
            [module.strip() for module in section[len("mypy-") :].split(",")] if section.startswith("mypy-") else []
        )
        if any(module == "permit" or module.startswith("permit.") for module in modules) and re.match(
            r"^(ignore_missing_imports\s*=\s*true|follow_imports\s*=\s*skip)", stripped, re.IGNORECASE
        ):
            hides_permit = True
        requirement_value = (section == "options" and key == "install_requires") or section == "options.extras_require"
        if requirement_value and value:
            facts.add_requirement(rel, number, value)
        if section == "options" and key == "python_requires" and not continuation:
            facts.add_python_pin(rel, number, stripped, below=python_below_310(value))
        if section == "metadata" and key == "classifiers":
            scan_classifiers(facts, rel, number, value)
        if section == "mypy" and not continuation:
            scan_version_setting(facts, rel, number, stripped)
        if section in ("pytest", "tool:pytest") and key in ("filterwarnings", "addopts"):
            scan_pytest_setting(facts, rel, number, value)
        if name == "tox.ini":
            tokens = [token for token in re.findall(r"\bpy3(\d{1,2})\b", raw) if int(token) < 10]
            tokens += [minor for minor in re.findall(r"\bpython3\.(\d+)\b", raw) if int(minor) < 10]
            if tokens:
                facts.add_python_pin(rel, number, stripped, below=True)
    close_section()


def scan_setup_py(facts: ProjectFacts, rel: str, tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if name != "setup":
            continue
        for keyword in node.keywords:
            if keyword.arg in ("install_requires", "tests_require"):
                for element in _string_elements(keyword.value):
                    facts.add_requirement(rel, element.lineno, str(element.value))
            elif keyword.arg == "extras_require" and isinstance(keyword.value, ast.Dict):
                for value in keyword.value.values:
                    for element in _string_elements(value):
                        facts.add_requirement(rel, element.lineno, str(element.value))
            elif keyword.arg == "python_requires" and isinstance(keyword.value, ast.Constant):
                spec = str(keyword.value.value)
                facts.add_python_pin(
                    rel, keyword.value.lineno, f'python_requires="{spec}"', below=python_below_310(spec)
                )
            elif keyword.arg == "classifiers":
                for element in _string_elements(keyword.value):
                    scan_classifiers(facts, rel, element.lineno, str(element.value))


def _string_elements(node: ast.AST) -> List[ast.Constant]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            element for element in node.elts if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
    return []


def scan_lock(facts: ProjectFacts, rel: str, lines: List[str]) -> None:
    """Only the locked permit version; the other pins in a lock file follow from the requirements."""
    for number, raw in enumerate(lines, 1):
        if re.match(r"^\s*name\s*=\s*\"permit\"\s*$", raw):
            for offset, following in enumerate(lines[number : number + 3], 1):
                match = re.match(r"^\s*version\s*=\s*\"([^\"]+)\"", following)
                if match:
                    _locked_permit(facts, rel, number + offset, match.group(1))
                    break
        if re.match(r"^\s*\"permit\"\s*:\s*\{", raw):
            for offset, following in enumerate(lines[number : number + 12], 1):
                match = re.match(r"^\s*\"version\"\s*:\s*\"==([^\"]+)\"", following)
                if match:
                    _locked_permit(facts, rel, number + offset, match.group(1))
                    break


def _locked_permit(facts: ProjectFacts, rel: str, number: int, version_text: str, *, compiled: bool = False) -> None:
    facts.locked_permit.append((rel, number, version_text))
    version = parse_version(version_text)
    if version is None or compare(version, (3,)) >= 0:
        return
    if compiled:
        message = (
            f"compiled requirements (a lock) pin permit {version_text}: don't edit this file; raise the "
            "requirement it is compiled from, then regenerate it with the command in its header"
        )
    else:
        message = f"locks permit {version_text}; regenerate the lock after raising the requirement"
    facts.findings.append(Finding(rel, number, "P1", SAFE, message))


def scan_python_version_file(facts: ProjectFacts, rel: str, lines: List[str]) -> None:
    """.python-version, runtime.txt and .tool-versions."""
    for number, raw in enumerate(lines, 1):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped:
            continue
        if Path(rel).name == ".tool-versions" and not stripped.startswith("python"):
            continue
        if re.search(r"(?<![\w.])3\.\d+", stripped):
            facts.add_python_pin(rel, number, stripped, below=bool(minors_below_310(stripped)))


_IMAGE_RE = re.compile(r"python:(\d+)\.(\d+)")
_CI_KEY_RE = re.compile(r"^\s*-?\s*[\"']?(python[-_ ]?versions?|python)[\"']?\s*:\s*(.*)$", re.IGNORECASE)


def scan_ci_or_dockerfile(facts: ProjectFacts, rel: str, lines: List[str]) -> None:
    """Python versions in CI configuration and Dockerfiles: images, python-version keys and lists."""
    list_indent: Optional[int] = None
    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if list_indent is not None:
            if stripped.startswith("-") and indent >= list_indent:
                if re.search(r"(?<![\w.])3\.\d+", stripped):
                    facts.add_python_pin(rel, number, stripped, below=bool(minors_below_310(stripped)))
                continue
            list_indent = None
        versions: List[str] = []
        image = _IMAGE_RE.search(raw)
        if image and image.group(1) == "3":
            versions.append(f"3.{image.group(2)}")
        key = _CI_KEY_RE.match(raw)
        if key and not key.group(2).split("#", 1)[0].strip():
            list_indent = indent
        elif key:
            versions.extend(re.findall(r"(?<![\w.])3\.\d+", key.group(2)))
        env = re.search(r"PYTHON_VERSION\s*[=:]\s*(.*)$", raw, re.IGNORECASE)
        if env:
            versions.extend(re.findall(r"(?<![\w.])3\.\d+", env.group(1)))
        if versions:
            facts.add_python_pin(rel, number, stripped, below=bool(minors_below_310(" ".join(versions))))


# ---------------------------------------------------------------------------
# Python source
# ---------------------------------------------------------------------------


def dotted(node: ast.AST) -> Optional[str]:
    """`a.b.c` for a chain of attributes on a name, otherwise None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def is_none(node: Optional[ast.AST]) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def bound_name(node: ast.AST) -> Optional[str]:
    """The name `node` binds, if it is a binding site: a target, parameter, import, def or except."""
    if isinstance(node, ast.Name):
        return node.id if isinstance(node.ctx, (ast.Store, ast.Del)) else None
    if isinstance(node, ast.arg):
        return node.arg
    if isinstance(node, ast.alias):
        return None if node.name == "*" else node.asname or node.name.split(".", 1)[0]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.ExceptHandler):
        return node.name
    # match statements (Python 3.10+): `case Point(x=px)` and `case {**rest}` bind names too.
    name = getattr(node, "rest", None) if type(node).__name__ == "MatchMapping" else None
    if type(node).__name__ in ("MatchAs", "MatchStar"):
        name = getattr(node, "name", None)
    return name if isinstance(name, str) else None


def is_async_mock(node: ast.AST) -> bool:
    """AsyncMock, mock.AsyncMock, or a call of either."""
    if isinstance(node, ast.Call):
        node = node.func
    return (isinstance(node, ast.Name) and node.id == "AsyncMock") or (
        isinstance(node, ast.Attribute) and node.attr == "AsyncMock"
    )


def async_mock_message(method: str) -> str:
    return (
        f"if this AsyncMock stands in for permit.sync.Permit.{method}(), use Mock or MagicMock with the same "
        "return_value: the method returns its result in 3.0, and an AsyncMock hands the code a coroutine"
    )


def combined(kinds: Set[str]) -> str:
    """One kind for a value bound in several places."""
    if MAYBE in kinds:
        return MAYBE
    if len(kinds) == 1:
        return next(iter(kinds))
    return EITHER


def union_members(node: Optional[ast.AST]) -> List[ast.AST]:
    """The types an annotation allows: X | Y, Optional[X] and Union[X, Y], also as a string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return []
    if node is None:
        return []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return union_members(node.left) + union_members(node.right)
    if isinstance(node, ast.Subscript):
        name = (dotted(node.value) or "").rsplit(".", 1)[-1]
        inner = node.slice
        if type(inner).__name__ == "Index":  # Python 3.8 wraps subscripts in ast.Index
            inner = getattr(inner, "value", inner)
        elements = inner.elts if isinstance(inner, ast.Tuple) else [inner]
        if name == "Optional":
            return [*union_members(elements[0]), ast.Constant(value=None)]
        if name == "Union":
            return [member for element in elements for member in union_members(element)]
    return [node]


def optional_annotation(node: Optional[ast.AST]) -> bool:
    """Optional[X], Union[X, None] or X | None, also as a string annotation."""
    return any(is_none(member) for member in union_members(node))


def guards(test: ast.AST, key: str, *, none_check: bool = True) -> bool:
    """Whether `test` being true means the value at `key` is usable: truthy, an isinstance()
    match, or (when `none_check`) `is not None`."""
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        return any(guards(value, key, none_check=none_check) for value in test.values)
    if (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.IsNot)
        and is_none(test.comparators[0])
    ):
        return none_check and dotted(test.left) == key
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "isinstance" and test.args:
        return dotted(test.args[0]) == key
    return dotted(test) == key


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
SCOPE_NODES = (*FUNCTIONS, *COMPREHENSIONS, ast.ClassDef, ast.Module)
GUARD_LIMITS = (*FUNCTIONS, ast.Module)
CLIENT_MEMBERS = {"api", "elements", "pdp_api", "authorized_users"}

# A name, or a chain such as self.permit, in the scope that binds it: (id of the scope node, name).
Slot = Tuple[int, str]


class SourceScan:
    """The findings in one Python file."""

    def __init__(self, rel: str, source: bytes, tree: ast.Module, project: "Project") -> None:
        self.rel = rel
        self.text = source.decode("utf-8", errors="replace")
        self.lines = self.text.splitlines()
        self.tree = tree
        self.project = project
        self.findings: List[Finding] = []
        self.parents: Dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent
        self.bound: Dict[int, Set[str]] = {}
        self.declared_global: Dict[int, Set[str]] = {}
        self.declared_nonlocal: Dict[int, Set[str]] = {}
        # Every place a slot is bound, other than to None. A traced value counts only when it
        # accounts for all of them: a name also bound to something else may not hold it.
        self.sites: Dict[Slot, Set[int]] = {}
        self.imported: Dict[Slot, str] = {}
        self.imports_permit = False
        self.client_annotations: Dict[Slot, Set[str]] = {}
        self.client_sites: Dict[Slot, Dict[int, str]] = {}
        self.handle_sites: Dict[Slot, Set[int]] = {}
        self.sdk_sites: Dict[Slot, Set[int]] = {}
        self.sdk_annotations: Set[Slot] = set()
        self.context_stores: Set[Slot] = set()
        self.optional_names: Set[Slot] = set()
        self.names_imported: Set[str] = set()
        self.star_imports: Set[str] = set()
        self.mentions_tuples = False

    def run(self) -> List[Finding]:
        self.collect_bindings()
        self.collect_imports()
        self.trace_values()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                self.check_call(node)
            elif isinstance(node, ast.Await):
                self.check_await(node)
            elif isinstance(node, ast.Assign):
                self.check_async_mock_assignment(node)
            elif isinstance(node, ast.Attribute):
                self.check_attribute(node)
            elif isinstance(node, ast.Name):
                self.check_star_imported_name(node)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.check_string(node)
        return self.findings

    # -- helpers ---------------------------------------------------------------

    def add(self, node: ast.AST, change: str, safety: str, message: str) -> None:
        self.findings.append(Finding(self.rel, getattr(node, "lineno", 1), change, safety, message))

    def source_of(self, node: ast.AST) -> str:
        segment = ast.get_source_segment(self.text, node)
        return segment if segment is not None else "..."

    def qualname(self, node: ast.AST) -> Optional[str]:
        """The permit name `node` refers to, through import aliases: SP.api -> permit.sync.Permit.api."""
        if isinstance(node, ast.Name):
            slot = self.slot(node)
            return self.imported.get(slot) if slot is not None else None
        if isinstance(node, ast.Attribute):
            base = self.qualname(node.value)
            return f"{base}.{node.attr}" if base else None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                expression = ast.parse(node.value, mode="eval").body
            except SyntaxError:
                return None
            return self.qualname(expression)
        return None

    # -- scopes ----------------------------------------------------------------

    def enclosing_scopes(self, node: ast.AST) -> Iterator[ast.AST]:
        """The scopes whose names `node` sees, innermost first.

        Defaults, annotations, decorators, base classes and a comprehension's first iterable are
        evaluated in the scope around the function, class or comprehension they belong to.
        """
        skip = False
        child = node
        parent = self.parents.get(node)
        while parent is not None:
            if (
                (isinstance(parent, ast.arguments) and (child in parent.defaults or child in parent.kw_defaults))
                or (isinstance(parent, ast.arg) and child is parent.annotation)
                or (
                    isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and (child in parent.decorator_list or child is parent.returns)
                )
                or (
                    isinstance(parent, ast.ClassDef)
                    and (child in parent.bases or child in parent.keywords or child in parent.decorator_list)
                )
            ):
                skip = True
            elif isinstance(parent, ast.comprehension) and child is parent.iter:
                owner = self.parents.get(parent)
                skip = isinstance(owner, COMPREHENSIONS) and owner.generators[0] is parent
            if isinstance(parent, SCOPE_NODES):
                if skip:
                    skip = False
                else:
                    yield parent
            child, parent = parent, self.parents.get(parent)

    def innermost_scope(self, site: ast.AST) -> ast.AST:
        """The scope a binding site binds in. A walrus in a comprehension binds in the enclosing one."""
        parent = self.parents.get(site)
        walrus = isinstance(parent, ast.NamedExpr) and parent.target is site
        for scope in self.enclosing_scopes(site):
            if not (walrus and isinstance(scope, COMPREHENSIONS)):
                return scope
        return self.tree

    def resolve(self, node: ast.AST, name: str) -> ast.AST:
        """The scope that binds `name` where `node` uses it, following Python's rules."""
        nested = False
        for scope in self.enclosing_scopes(node):
            if isinstance(scope, ast.Module):
                return scope
            if isinstance(scope, ast.ClassDef):
                # A class body's names are visible in the body itself, not in its methods.
                if not nested and name in self.bound.get(id(scope), ()):
                    return scope
                continue
            nested = True
            if name in self.declared_global.get(id(scope), ()):
                return self.tree
            if name in self.bound.get(id(scope), ()):
                return scope
        return self.tree

    def enclosing_class(self, node: ast.AST) -> Optional[ast.ClassDef]:
        current = self.parents.get(node)
        while current is not None and not isinstance(current, ast.ClassDef):
            current = self.parents.get(current)
        return current

    def slot(self, node: ast.AST) -> Optional[Slot]:
        """Where the value `node` names is bound: a name's scope, or the class for self.x and cls.x."""
        key = dotted(node)
        if key is None:
            return None
        root = key.split(".", 1)[0]
        if "." in key and root in ("self", "cls"):
            owner = self.enclosing_class(node)
            if owner is not None:
                return (id(owner), key)
        return (id(self.resolve(node, root)), key)

    def target_slots(self, target: ast.AST) -> List[Slot]:
        """The slots an assignment target binds. A name in a class body is also self.name."""
        slot = self.slot(target)
        if slot is None:
            return []
        slots = [slot]
        if isinstance(target, ast.Name):
            scope = self.resolve(target, target.id)
            if isinstance(scope, ast.ClassDef):
                slots.append((id(scope), f"self.{target.id}"))
        return slots

    def collect_bindings(self) -> None:
        """Which names each scope binds, and every site that binds a slot."""
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                declared = self.declared_global if isinstance(node, ast.Global) else self.declared_nonlocal
                declared.setdefault(id(self.innermost_scope(node)), set()).update(node.names)
        sites: List[Tuple[str, ast.AST]] = []
        for node in ast.walk(self.tree):
            name = bound_name(node)
            if name is None:
                continue
            sites.append((name, node))
            scope = id(self.innermost_scope(node))
            elsewhere = self.declared_global.get(scope, set()) | self.declared_nonlocal.get(scope, set())
            if name not in elsewhere:
                self.bound.setdefault(scope, set()).add(name)
        for name, node in sites:
            if self.binds_none(node):
                continue
            named = isinstance(node, ast.Name)
            slots = self.target_slots(node) if named else [(id(self.resolve(node, name)), name)]
            for slot in slots:
                self.sites.setdefault(slot, set()).add(id(node))
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) and not self.binds_none(node):
                for slot in self.target_slots(node):
                    self.sites.setdefault(slot, set()).add(id(node))

    def binds_none(self, target: ast.AST) -> bool:
        """`x = None` or `x: T` with no value: a placeholder, not another value `x` may hold."""
        parent = self.parents.get(target)
        if isinstance(parent, ast.Assign) and target in parent.targets:
            return is_none(parent.value)
        if isinstance(parent, ast.AnnAssign) and parent.target is target:
            return parent.value is None or is_none(parent.value)
        return False

    # -- traced values ---------------------------------------------------------

    def bind(self, table: Dict[Slot, Set[int]], target: ast.AST) -> None:
        for slot in self.target_slots(target):
            table.setdefault(slot, set()).add(id(target))

    def bind_client(self, target: ast.AST, kind: str) -> None:
        for slot in self.target_slots(target):
            self.client_sites.setdefault(slot, {})[id(target)] = kind

    def mark(self, table: Set[Slot], target: ast.AST) -> None:
        slot = self.slot(target)
        if slot is not None:
            table.add(slot)

    def holds_only(self, slot: Optional[Slot], site_ids: Optional[Set[int]]) -> bool:
        """Whether the traced sites account for every site that binds the slot."""
        return slot is not None and bool(site_ids) and self.sites.get(slot, set()) <= (site_ids or set())

    def client_kind(self, node: ast.AST) -> Optional[str]:
        """ASYNC, SYNC, EITHER or MAYBE when `node` is traced to a permit client, otherwise None."""
        if isinstance(node, ast.Call):
            return self.class_kind(node.func)
        slot = self.slot(node)
        if slot is None:
            return None
        annotated = self.client_annotations.get(slot)
        if annotated:
            return combined(annotated)
        assigned = self.client_sites.get(slot)
        if not assigned:
            return None
        if not self.holds_only(slot, set(assigned)):
            return MAYBE
        return combined(set(assigned.values()))

    def is_client(self, node: ast.AST) -> bool:
        return self.client_kind(node) in CLIENTS

    def class_kind(self, annotation: Optional[ast.AST]) -> Optional[str]:
        if annotation is None:
            return None
        kinds = set()
        for node in ast.walk(annotation):
            name = self.qualname(node)
            if name in ASYNC_CLIENTS:
                kinds.add(ASYNC)
            elif name in SYNC_CLIENTS:
                kinds.add(SYNC)
        return combined(kinds) if kinds else None

    def is_api_handle(self, node: ast.AST) -> bool:
        slot = self.slot(node)
        return slot is not None and self.holds_only(slot, self.handle_sites.get(slot))

    def client_behind(self, func: ast.AST) -> Optional[ast.AST]:
        """The client expression before `.api`, `.elements`, `.pdp_api` or `.authorized_users` in a chain."""
        node = func
        while isinstance(node, ast.Attribute):
            if node.attr in CLIENT_MEMBERS and self.is_client(node.value):
                return node.value
            node = node.value
        return None

    def api_receiver(self, func: ast.Attribute) -> Tuple[Optional[ast.AST], bool]:
        """(the expression holding `.api`, whether it is a traced client) for x.api....method."""
        node: ast.AST = func.value
        while isinstance(node, ast.Attribute):
            if node.attr == "api":
                return node.value, self.is_client(node.value)
            node = node.value
        if self.is_api_handle(node):
            return node, True
        return None, False

    def is_api_call(self, node: ast.AST) -> bool:
        """A call through a traced client that returns an SDK model, such as permit.api.users.get()."""
        if isinstance(node, ast.Await):
            node = node.value
        if not isinstance(node, ast.Call):
            return False
        if self.client_behind(node.func) is not None:
            return True
        root = node.func
        while isinstance(root, ast.Attribute):
            root = root.value
        return self.is_api_handle(root)

    def sdk_class(self, node: ast.AST) -> Optional[str]:
        """The qualified name when `node` is a class imported from permit, other than the clients."""
        name = self.qualname(node)
        if name is None or not name.startswith("permit.") or name in ASYNC_CLIENTS or name in SYNC_CLIENTS:
            return None
        return name if name.rsplit(".", 1)[-1][:1].isupper() else None

    def is_sdk_value(self, node: ast.AST) -> bool:
        if self.sdk_class(node) is not None or self.is_api_call(node):
            return True
        slot = self.slot(node)
        if slot in self.sdk_annotations:
            return True
        return slot is not None and self.holds_only(slot, self.sdk_sites.get(slot))

    # -- imports ---------------------------------------------------------------

    def import_as(self, alias: ast.alias, qualname: str) -> None:
        name = bound_name(alias)
        if name is not None:
            self.imported[(id(self.resolve(alias, name)), name)] = qualname

    def collect_imports(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".", 1)[0]
                    self.check_transitive_import(node, top)
                    if top in TRACED_MODULES:
                        self.import_as(alias, alias.name if alias.asname else top)
                    if top != "permit":
                        continue
                    self.imports_permit = True
                    self.check_import_comment(node)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                top = node.module.split(".", 1)[0]
                self.check_transitive_import(node, top)
                if top == "asyncio":
                    for alias in node.names:
                        self.import_as(alias, f"{node.module}.{alias.name}")
                if top != "permit":
                    continue
                self.imports_permit = True
                self.check_import_comment(node)
                for alias in node.names:
                    if alias.name == "*":
                        self.star_imports.add(node.module)
                        continue
                    self.import_as(alias, f"{node.module}.{alias.name}")
                    self.names_imported.add(alias.name)
                    self.check_removed(node, node.module, alias.name)
                    self.check_model_import(node, node.module, alias.name)

    def check_import_comment(self, node: ast.stmt) -> None:
        """An ignore comment on a permit import: SAFE to drop when it only silenced the missing types."""
        end = node.end_lineno or node.lineno
        for number in range(node.lineno, end + 1):
            line = self.lines[number - 1] if number <= len(self.lines) else ""
            match = re.search(r"#\s*(?:type|pyright):\s*ignore(?:\[([^\]]*)\])?", line)
            if match is None:
                continue
            codes = {code.strip() for code in (match.group(1) or "").split(",") if code.strip()}
            if codes <= IMPORT_IGNORE_CODES:
                self.findings.append(
                    Finding(self.rel, number, "T1", SAFE, "permit ships py.typed now: remove this ignore comment")
                )
            else:
                self.findings.append(
                    Finding(
                        self.rel,
                        number,
                        "T1",
                        REVIEW,
                        f"permit ships py.typed now: drop the import codes from this ignore; check what "
                        f"{', '.join(sorted(codes - IMPORT_IGNORE_CODES))} hides",
                    )
                )

    def check_transitive_import(self, node: ast.stmt, top: str) -> None:
        if top not in TRANSITIVE_PACKAGES or top in self.project.declared:
            return
        if top == "httpx":
            self.add(node, "C2", SAFE, "permit 3 no longer installs httpx: declare httpx>=0.24.1,<1 yourself")
        else:
            self.add(
                node,
                "C2",
                REVIEW,
                f"{top} is not declared, and {TRANSITIVE_PACKAGES[top]}: declare it unless another "
                "dependency still brings it",
            )

    def check_removed(self, node: ast.AST, module: str, name: str) -> None:
        entry = REMOVED.get((module, name))
        if entry is not None:
            change, safety, message = entry
            self.add(node, change, safety, f"{module}.{name} does not exist in permit 3: {message}")

    def check_star_imported_name(self, node: ast.Name) -> None:
        """ApiKeyLevel after `from permit.api.context import *`, unless the file binds the name itself."""
        if not self.star_imports or not isinstance(node.ctx, ast.Load):
            return
        if self.resolve(node, node.id) is not self.tree or node.id in self.bound.get(id(self.tree), set()):
            return
        for module in sorted(self.star_imports):
            if (module, node.id) in REMOVED:
                self.check_removed(node, module, node.id)
                return

    def check_model_import(self, node: ast.stmt, module: str, name: str) -> None:
        if module not in MODEL_MODULES or name not in NEW_ENUM_MEMBERS:
            return
        change, member = NEW_ENUM_MEMBERS[name]
        new_member = member.rsplit(".", 1)[-1]
        if any(isinstance(other, ast.Attribute) and other.attr == new_member for other in ast.walk(self.tree)):
            return
        self.add(node, change, REVIEW, f"{member} is new in 3.0: check code that handles every member of {name}")

    # -- tracing ---------------------------------------------------------------

    def trace_values(self) -> None:
        """Record which names hold permit clients, `client.api` handles, SDK models and context stores."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute) and node.attr == "relationship_tuples":
                self.mentions_tuples = True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for argument in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                    self.annotate([(id(node), argument.arg)], argument.annotation)
                for name in self.optional_parameters(node):
                    self.optional_names.add((id(node), name))
            elif isinstance(node, ast.AnnAssign):
                self.annotate(self.target_slots(node.target), node.annotation)
                if optional_annotation(node.annotation):
                    self.mark(self.optional_names, node.target)
        # Assignments after annotations, twice, so that `b = a` sees what `a` holds whatever their order.
        for _ in range(2):
            for node in ast.walk(self.tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        self.trace_assignment(target, node.value)
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    self.trace_assignment(node.target, node.value)
                elif isinstance(node, (ast.For, ast.AsyncFor)) and self.is_api_call(node.iter):
                    self.bind(self.sdk_sites, node.target)

    def annotate(self, slots: List[Slot], annotation: Optional[ast.AST]) -> None:
        """A client or SDK model annotation decides what the name holds, whatever else it is assigned."""
        kind = self.class_kind(annotation)
        if kind is not None:
            for slot in slots:
                self.client_annotations.setdefault(slot, set()).add(kind)
        elif self.model_annotation(annotation):
            self.sdk_annotations.update(slots)

    def model_annotation(self, annotation: Optional[ast.AST]) -> bool:
        """UserRead, Optional[UserRead] or "UserRead | None" for a model class imported from permit."""
        members = [member for member in union_members(annotation) if not is_none(member)]
        return bool(members) and all(
            (self.sdk_class(member) or "").rsplit(".", 1)[0] in MODEL_MODULES for member in members
        )

    def optional_parameters(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> List[str]:
        """Parameters annotated Optional (or `X | None`) or defaulting to None."""
        found = []
        positional = node.args.posonlyargs + node.args.args
        offset = len(positional) - len(node.args.defaults)
        for index, argument in enumerate(positional):
            default = node.args.defaults[index - offset] if index >= offset else None
            if optional_annotation(argument.annotation) or is_none(default):
                found.append(argument.arg)
        for index, argument in enumerate(node.args.kwonlyargs):
            if optional_annotation(argument.annotation) or is_none(node.args.kw_defaults[index]):
                found.append(argument.arg)
        return found

    def guarded(self, node: ast.AST, *, none_check: bool = True) -> bool:
        """Whether an enclosing `if`, conditional expression, `and` or comprehension checks `node` first.

        With `none_check` false, `is not None` does not count: only truthiness and isinstance() do.
        """
        key = dotted(node)
        if key is None:
            return False
        child: ast.AST = node
        parent = self.parents.get(node)
        while parent is not None and not isinstance(parent, GUARD_LIMITS):
            if isinstance(parent, ast.If) and child in parent.body and guards(parent.test, key, none_check=none_check):
                return True
            if (
                isinstance(parent, ast.IfExp)
                and child is parent.body
                and guards(parent.test, key, none_check=none_check)
            ):
                return True
            if isinstance(parent, ast.BoolOp) and isinstance(parent.op, ast.And):
                earlier: List[ast.expr] = []
                for value in parent.values:
                    if value is child:
                        break
                    earlier.append(value)
                if any(guards(value, key, none_check=none_check) for value in earlier):
                    return True
            if isinstance(parent, COMPREHENSIONS):
                tests = [test for generator in parent.generators for test in generator.ifs]
                if child not in parent.generators and any(guards(test, key, none_check=none_check) for test in tests):
                    return True
            child, parent = parent, self.parents.get(parent)
        return False

    def maybe_none(self, node: ast.AST) -> bool:
        """Whether `node` is visibly None or optional: None, `a if c else None`, `.get(k)`, an Optional name."""
        if isinstance(node, ast.Constant):
            return node.value is None
        if isinstance(node, ast.IfExp):
            return self.maybe_none(node.body) or self.maybe_none(node.orelse)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get" and not node.keywords:
                return len(node.args) == 1 or (len(node.args) == 2 and is_none(node.args[1]))
            if isinstance(func, ast.Name) and func.id == "getattr":
                return len(node.args) == 3 and is_none(node.args[2])
            return False
        if isinstance(node, ast.Name) and not self.guarded(node):
            return self.slot(node) in self.optional_names
        return False

    def trace_assignment(self, target: ast.AST, value: ast.AST) -> None:
        if isinstance(value, ast.Await):
            value = value.value
        kind = self.client_kind(value)
        if kind is not None:
            self.bind_client(target, kind)
        elif isinstance(value, ast.Attribute) and value.attr == "api" and self.is_client(value.value):
            self.bind(self.handle_sites, target)
        elif (isinstance(value, ast.Call) and self.qualname(value.func) == "permit.utils.context.ContextStore") or (
            isinstance(value, ast.Attribute) and value.attr == "context_store"
        ):
            self.mark(self.context_stores, target)
        elif self.is_api_call(value) or (isinstance(value, ast.Call) and self.is_model_construction(value)):
            self.bind(self.sdk_sites, target)

    def is_model_construction(self, call: ast.Call) -> bool:
        """UserRead(...) or UserRead.parse_obj(...) for a class imported from permit."""
        if self.sdk_class(call.func) is not None:
            return True
        return isinstance(call.func, ast.Attribute) and self.sdk_class(call.func.value) is not None

    # -- checks ----------------------------------------------------------------

    def check_call(self, node: ast.Call) -> None:
        func = node.func
        self.check_request_model(node)
        self.check_runner_argument(node)
        self.check_async_mock(node)
        if not isinstance(func, ast.Attribute):
            return
        self.check_deprecated_call(node, func)
        relations = isinstance(func.value, ast.Attribute) and func.value.attr == "resource_relations"
        if func.attr == "list" and relations and not self.reads_page(node):
            self.add(
                node,
                "A1",
                REVIEW,
                "resource_relations.list() returns PaginatedResultRelationRead: read `.data`. "
                "It raised ValidationError on every call before 3.0",
            )
        if func.attr == "register_transform" and self.imports_permit:
            self.add(
                node,
                "A3",
                REVIEW,
                "ContextStore.register_transform() is removed, and the SDK never applied a registered transform "
                "to a check: delete the call, or apply the transform to the context you pass to check()",
            )
        context_store = isinstance(func.value, ast.Attribute) and func.value.attr == "context_store"
        if func.attr == "transform" and (context_store or self.slot(func.value) in self.context_stores):
            self.add(
                node,
                "A3",
                REVIEW,
                "ContextStore.transform() is removed. It applied the functions registered with register_transform() "
                "(the SDK itself never called it): call those functions on the context directly",
            )
        self.check_v2_method(node, func)
        self.check_api_dicts(node, func)

    def reads_page(self, call: ast.Call) -> bool:
        """Whether the call's result is read as a page: `(await x.list(r)).data`, or a name later read so."""
        parent = self.parents.get(call)
        if isinstance(parent, ast.Await):
            parent = self.parents.get(parent)
        if isinstance(parent, ast.Attribute) and parent.attr in PAGE_FIELDS:
            return True
        if not isinstance(parent, (ast.Assign, ast.AnnAssign)):
            return False
        targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
        assigned = {self.slot(target) for target in targets} - {None}
        return any(
            isinstance(other, ast.Attribute) and other.attr in PAGE_FIELDS and self.slot(other.value) in assigned
            for other in ast.walk(self.tree)
        )

    def check_deprecated_call(self, node: ast.Call, func: ast.Attribute) -> None:
        if func.attr not in DEPRECATED_METHODS:
            return
        via_api = False
        untraced = ""
        if isinstance(func.value, ast.Attribute) and func.value.attr == "api":
            via_api = True
            client = self.source_of(func.value.value)
            if not self.is_client(func.value.value):
                untraced = f"`{client}` is not traced to a permit client in this file"
        elif self.is_api_handle(func.value):
            client = f"<the client behind {self.source_of(func.value)}>"
        elif isinstance(func.value, ast.Name) and func.value.id.endswith("api") and self.imports_permit:
            # Named like a `client.api` handle, but bound to something this file doesn't trace.
            client = f"<the client behind {func.value.id}>"
            untraced = f"`{func.value.id}` is not traced to a permit client's .api in this file"
        else:
            return
        traced = not untraced
        replacement, renames = DEPRECATED_METHODS[func.attr]
        if not via_api and replacement.startswith("api."):
            target = f"{self.source_of(func.value)}.{replacement[len('api.') :]}"
        else:
            target = f"{client}.{replacement}"
        starred = any(isinstance(arg, ast.Starred) for arg in node.args) or any(
            keyword.arg is None for keyword in node.keywords
        )
        if renames is None:
            argument = self.assignment_argument(node)
            detail = f"use {target}({argument or '...'})"
            safe = traced and argument is not None
        else:
            renamed = [f"{kw.arg}= to {renames[kw.arg]}=" for kw in node.keywords if kw.arg in renames]
            detail = f"use {target}(...)" + (f" and rename {', '.join(renamed)}" if renamed else "")
            safe = traced and not starred
        if not traced:
            detail = f"{untraced}; if it is one, {detail}"
        old = f"permit.api.{func.attr}()"
        self.add(node, "D2", SAFE if safe else REVIEW, f"{old} is deprecated and removed in 4.0: {detail}")

    def assignment_argument(self, node: ast.Call) -> Optional[str]:
        """The dict that replaces assign_role(user_key, role_key, tenant_key)'s three arguments."""
        order = ["user", "role", "tenant"]
        if any(isinstance(arg, ast.Starred) for arg in node.args) or len(node.args) > len(order):
            return None
        values = {order[index]: self.source_of(arg) for index, arg in enumerate(node.args)}
        for keyword in node.keywords:
            if keyword.arg not in ASSIGNMENT_KEYS:
                return None
            values[ASSIGNMENT_KEYS[keyword.arg]] = self.source_of(keyword.value)
        if set(values) != set(order):
            return None
        return "{" + ", ".join(f'"{name}": {values[name]}' for name in order) + "}"

    def check_await(self, node: ast.Await) -> None:
        call = node.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            return
        method = call.func.attr
        if method not in NOW_SYNC_METHODS:
            return
        receiver = call.func.value
        kind = self.client_kind(receiver)
        if kind == SYNC:
            self.add(
                node,
                "A2",
                REVIEW,
                f"`{self.source_of(receiver)}` is a permit.sync.Permit, whose {method}() returns its result in "
                "3.0 and blocks while it waits. This is async code: switch it to the async permit.Permit and "
                "keep the await (recommended), or drop the await and accept a blocking call",
            )
        elif kind in (EITHER, MAYBE) or (kind is None and self.project.uses_sync_client):
            self.add(node, "A2", REVIEW, self.untraced_a2(receiver, method))

    def untraced_a2(self, receiver: ast.AST, method: str) -> str:
        return (
            f"if `{self.source_of(receiver)}` is a permit.sync.Permit, {method}() returns its result in 3.0: "
            "call it without await or a coroutine runner. The async permit.Permit still needs them"
        )

    def coroutine_runner(self, func: ast.AST) -> Optional[Tuple[str, bool]]:
        """(name, whether it runs a coroutine to completion from sync code) for a coroutine runner."""
        name = self.qualname(func)
        if name is not None and name.startswith("asyncio."):
            short = name[len("asyncio.") :]
        elif isinstance(func, ast.Attribute):
            short = func.attr
        else:
            return None
        if short not in COROUTINE_RUNNERS:
            return None
        return short, name == "asyncio.run" or short == "run_until_complete"

    def check_runner_argument(self, node: ast.Call) -> None:
        """asyncio.run(client.filter_objects(...)) and other runners given one of the three methods."""
        runner = self.coroutine_runner(node.func)
        if runner is None:
            return
        name, from_sync_code = runner
        for arg in node.args:
            if not (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)):
                continue
            method = arg.func.attr
            if method not in NOW_SYNC_METHODS:
                continue
            kind = self.client_kind(arg.func.value)
            if kind == SYNC and from_sync_code:
                self.add(
                    arg,
                    "A2",
                    SAFE,
                    f"permit.sync.Permit.{method}() returns its result in 3.0, and {name}() raises on it: "
                    "call the method directly",
                )
            elif kind == SYNC:
                self.add(
                    arg,
                    "A2",
                    REVIEW,
                    f"permit.sync.Permit.{method}() returns its result in 3.0 and blocks while it waits, so "
                    f"{name}() gets no coroutine. This is async code: switch it to the async permit.Permit "
                    "(recommended), or call the method directly and accept a blocking call",
                )
            elif kind in (EITHER, MAYBE) or (kind is None and self.project.uses_sync_client):
                self.add(arg, "A2", REVIEW, self.untraced_a2(arg.func.value, method))

    def check_async_mock(self, node: ast.Call) -> None:
        """patch(..., new_callable=AsyncMock) or setattr(x, "method", AsyncMock()) for the three methods."""
        if not self.project.uses_sync_client:
            return
        values = list(node.args) + [keyword.value for keyword in node.keywords]
        if not any(is_async_mock(value) for value in values):
            return
        if node.args and (self.client_kind(node.args[0]) == ASYNC or self.qualname(node.args[0]) in ASYNC_CLIENTS):
            return
        for arg in node.args:
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            owner, _, method = arg.value.rpartition(".")
            if method in NOW_SYNC_METHODS and owner not in ASYNC_CLIENTS:
                self.add(node, "A2", REVIEW, async_mock_message(method))
                return

    def check_async_mock_assignment(self, node: ast.Assign) -> None:
        """client.authorized_users = AsyncMock(...)"""
        if not self.project.uses_sync_client or not is_async_mock(node.value):
            return
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr in NOW_SYNC_METHODS
                and self.client_kind(target.value) != ASYNC
                and self.qualname(target.value) not in ASYNC_CLIENTS
            ):
                self.add(target, "A2", REVIEW, async_mock_message(target.attr))

    def check_v2_method(self, node: ast.Call, func: ast.Attribute) -> None:
        if func.attr not in V2_METHODS or not self.is_sdk_value(func.value):
            return
        v1_name, shared = V2_METHODS[func.attr]
        unsupported = [keyword.arg or "**" for keyword in node.keywords if keyword.arg not in shared]
        if func.attr in ("model_validate", "model_validate_json") and len(node.args) != 1:
            unsupported.append("the arguments")
        message = f"SDK models are pydantic v1 models, with no .{func.attr}(): use .{v1_name}()"
        if unsupported:
            self.add(node, "T2", REVIEW, f"{message}, which does not take {', '.join(unsupported)}")
        else:
            self.add(node, "T2", SAFE, message)

    def check_attribute(self, node: ast.Attribute) -> None:
        name = self.qualname(node)
        if name is not None:
            module, _, attr = name.rpartition(".")
            self.check_removed(node, module, attr)
        if node.attr in V2_ATTRIBUTES and self.is_sdk_value(node.value):
            safety = SAFE if node.attr == "model_fields_set" else REVIEW
            replacement = V2_ATTRIBUTES[node.attr]
            self.add(node, "T2", safety, f"SDK models are pydantic v1 models: use .{replacement}, not .{node.attr}")
        inner = node.value
        if not isinstance(inner, ast.Attribute):
            return
        if inner.attr == "objects" and "DetailedAuditLogModel" in self.names_imported:
            # A log without objects gets the field's default, {}, which `is not None` lets through.
            if not self.guarded(inner, none_check=False):
                self.add(
                    node,
                    "A4",
                    REVIEW,
                    "DetailedAuditLogModel.objects is {} (a plain dict) when a log has no objects, and None when "
                    "the API sends null: check isinstance(..., AuditLogObjectsModel) before reading it",
                )
            return
        if self.guarded(inner):
            return
        if inner.attr == "pdp_config_id" and self.names_imported & AUDIT_LOG_MODELS:
            self.add(node, "A4", REVIEW, "pdp_config_id may be None in 3.0: check it before using it")
        elif inner.attr in TUPLE_OPTIONAL_FIELDS and (self.mentions_tuples or self.names_imported & TUPLE_MODELS):
            self.add(node, "A5", REVIEW, f"{inner.attr} may be None in 3.0: check it before using it")

    def check_string(self, node: ast.Constant) -> None:
        if OLD_D2_TEXT_RE.search(str(node.value)):
            self.add(node, "D2", REVIEW, OLD_D2_FILTER)
        if self.imports_permit and re.match(r"bearer(\s|$)", str(node.value)):
            self.add(
                node,
                "W5",
                REVIEW,
                "permit 3 sends `Authorization: Bearer ...` with a capital B: update this if it matches "
                "permit's header",
            )

    def check_request_model(self, node: ast.Call) -> None:
        name = self.sdk_class(node.func)
        if name is None or name.rsplit(".", 1)[0] not in MODEL_MODULES:
            return
        short = name.rsplit(".", 1)[-1]
        if not short.endswith(REQUEST_MODEL_SUFFIXES):
            return
        explicit = [keyword.arg for keyword in node.keywords if keyword.arg and is_none(keyword.value)]
        optional = [
            keyword.arg
            for keyword in node.keywords
            if keyword.arg and not is_none(keyword.value) and self.maybe_none(keyword.value)
        ]
        if explicit:
            arguments = ", ".join(f"{arg}=None" for arg in explicit)
            self.add(
                node,
                "W1",
                REVIEW,
                f"{short}({arguments}) now sends null and clears the field: leave the argument out to keep "
                "the current value",
            )
        elif optional:
            self.add(
                node,
                "W1",
                REVIEW,
                f"{short}: when {', '.join(optional)} is None, permit 3 sends null and clears the field; "
                "pass it only when it has a value",
            )

    def check_api_dicts(self, node: ast.Call, func: ast.Attribute) -> None:
        holder, traced = self.api_receiver(func)
        if holder is None or not (traced or self.imports_permit):
            return
        for arg in list(node.args) + [keyword.value for keyword in node.keywords]:
            if not isinstance(arg, ast.Dict):
                continue
            values = [value for index, value in enumerate(arg.values) if arg.keys[index] is not None]
            if any(self.maybe_none(value) for value in values):
                self.add(
                    arg,
                    "W1",
                    REVIEW,
                    "a None value in this body is now sent as null and clears the field: leave the key out "
                    "to keep the current value",
                )


# ---------------------------------------------------------------------------
# Project walk
# ---------------------------------------------------------------------------


class Project:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.facts = ProjectFacts()
        self.skipped: List[Dict[str, str]] = []
        self.declared: Set[str] = set()
        self.uses_sync_client = False
        self.own_dir = Path(__file__).resolve().parent.parent

    def files(self) -> Iterator[Path]:
        for directory, subdirectories, filenames in os.walk(self.root):
            here = Path(directory)
            subdirectories[:] = sorted(
                name
                for name in subdirectories
                if name not in SKIP_DIRS
                and not name.endswith(".egg-info")
                and not (here / name / "pyvenv.cfg").exists()
                and (here / name).resolve() != self.own_dir
            )
            for filename in sorted(filenames):
                yield here / filename

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def read_lines(self, path: Path) -> Optional[List[str]]:
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            self.skipped.append({"path": self.rel(path), "reason": str(error)})
            return None

    def scan(self) -> List[Finding]:
        self.facts = ProjectFacts()
        self.skipped = []
        python_files: List[Path] = []
        for path in self.files():
            name = path.name
            rel = self.rel(path)
            if name.endswith(".py"):
                python_files.append(path)
            if name == "setup.py":
                continue
            kind = self.config_kind(path)
            if kind is None:
                continue
            lines = self.read_lines(path)
            if lines is None:
                continue
            if kind == "requirements":
                scan_requirements_txt(self.facts, rel, lines)
            elif kind == "pyproject":
                scan_toml(self.facts, rel, lines, pipfile=False)
            elif kind == "pipfile":
                scan_toml(self.facts, rel, lines, pipfile=True)
            elif kind == "ini":
                scan_ini(self.facts, rel, lines)
            elif kind == "lock":
                scan_lock(self.facts, rel, lines)
            elif kind == "version-file":
                scan_python_version_file(self.facts, rel, lines)
            elif kind in ("ci", "docker"):
                scan_ci_or_dockerfile(self.facts, rel, lines)
            elif kind == "pyright":
                for number, raw in enumerate(lines, 1):
                    scan_version_setting(self.facts, rel, number, raw)

        trees: List[Tuple[Path, bytes, ast.Module]] = []
        for path in python_files:
            try:
                source = path.read_bytes()
                tree = ast.parse(source, filename=str(path))
            except (OSError, SyntaxError, ValueError) as error:
                self.skipped.append({"path": self.rel(path), "reason": f"{type(error).__name__}: {error}"})
                continue
            trees.append((path, source, tree))
            if path.name == "setup.py":
                scan_setup_py(self.facts, self.rel(path), tree)
            if re.search(rb"\bpermit\.sync\b|\bfrom\s+permit\s+import\s+[^\n]*\bsync\b", source):
                self.uses_sync_client = True

        self.declared = self.facts.declared()
        findings = list(self.facts.findings)
        findings.extend(self.requirement_findings())
        for path, source, tree in trees:
            findings.extend(SourceScan(self.rel(path), source, tree, self).run())
        return sorted(set(findings), key=lambda finding: (finding.path, finding.line, finding.change, finding.message))

    def config_kind(self, path: Path) -> Optional[str]:
        name = path.name
        parent = path.parent.name
        if re.match(r"(requirements|constraints).*\.(txt|in)$", name) or (
            parent == "requirements" and name.endswith((".txt", ".in"))
        ):
            return "requirements"
        if name == "pyproject.toml":
            return "pyproject"
        if name == "Pipfile":
            return "pipfile"
        if name in ("setup.cfg", "tox.ini", "mypy.ini", ".mypy.ini", "pytest.ini"):
            return "ini"
        if name in LOCK_FILES:
            return "lock"
        if name in (".python-version", "runtime.txt", ".tool-versions"):
            return "version-file"
        if name == "pyrightconfig.json":
            return "pyright"
        if name in ("Dockerfile", "Containerfile") or name.startswith("Dockerfile.") or name.endswith(".Dockerfile"):
            return "docker"
        workflow = parent == "workflows" and path.parent.parent.name == ".github"
        if (workflow and name.endswith((".yml", ".yaml"))) or name in CI_FILE_NAMES:
            return "ci"
        if parent == ".circleci" and name == "config.yml":
            return "ci"
        return None

    def requirement_findings(self) -> List[Finding]:
        findings: List[Finding] = []
        for requirement in self.facts.requirements:
            alternatives = parse_spec(requirement.spec) if requirement.spec != "@" else None
            where = (requirement.path, requirement.line)
            if requirement.name == "permit":
                if alternatives is None:
                    findings.append(
                        Finding(
                            *where, "P1", REVIEW, f"`{requirement.text}`: make sure it resolves to permit>=3.0.0,<4"
                        )
                    )
                elif intersects(alternatives, None, (3,)) or not intersects(alternatives, (3,), (4,)):
                    findings.append(Finding(*where, "P1", SAFE, f"`{requirement.text}`: change it to permit>=3.0.0,<4"))
            if alternatives is None:
                continue
            ranges = FLOORS.get(requirement.name)
            if ranges and not any(intersects(alternatives, low, high) for low, high in ranges):
                findings.append(
                    Finding(
                        *where,
                        "C3",
                        SAFE,
                        f"`{requirement.text}` is below permit 3's floor: raise it to {FLOOR_TEXT[requirement.name]}",
                    )
                )
            if requirement.name == "pydantic" and not intersects(alternatives, (2,), None):
                findings.append(
                    Finding(
                        *where,
                        "D1",
                        REVIEW,
                        f"`{requirement.text}` holds pydantic 1, which permit 3 deprecates and permit 4 drops; "
                        "plan the move to pydantic 2",
                    )
                )
        if self.facts.pins_pydantic1() and not self.facts.pydantic1_filter_present:
            for path, line in self.facts.pytest_error_filters:
                findings.append(
                    Finding(
                        path,
                        line,
                        "D1",
                        REVIEW,
                        "warnings are errors here, and `import permit` warns on pydantic 1: add "
                        "`ignore:Support for pydantic 1:DeprecationWarning` or move to pydantic 2",
                    )
                )
        return findings

    def summary(self) -> Dict[str, object]:
        def requirement_list(name: str) -> List[str]:
            return [f"{item.path}:{item.line}: {item.text}" for item in self.facts.requirements if item.name == name]

        return {
            "permit_requirements": requirement_list("permit"),
            "permit_locked": [f"{path}:{line}: {version}" for path, line, version in self.facts.locked_permit],
            "pydantic_requirements": requirement_list("pydantic"),
            "python_pins": [f"{path}:{line}: {text}" for path, line, text in self.facts.python_pins],
            "uses_sync_client": self.uses_sync_client,
            "httpx_declared": "httpx" in self.declared,
        }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find what a permit 2.x -> 3.0.0 upgrade touches in a project.")
    parser.add_argument("path", nargs="?", default=".", help="project directory (default: the current directory)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    arguments = parser.parse_args(argv)
    root = Path(arguments.path)
    if not root.is_dir():
        parser.error(f"not a directory: {arguments.path}")

    project = Project(root.resolve())
    findings = project.scan()
    changes = {change: TITLES[change] for change in sorted({finding.change for finding in findings})}
    if arguments.json:
        report = {
            "root": str(project.root),
            "findings": [finding._asdict() for finding in findings],
            "changes": changes,
            "summary": project.summary(),
            "skipped": project.skipped,
        }
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0

    out: List[str] = []
    for key, value in project.summary().items():
        if isinstance(value, list):
            out.append(f"{key}:" + ("" if value else " none"))
            out.extend(f"  {item}" for item in value)
        else:
            out.append(f"{key}: {value}")
    out.append("")
    out.extend(
        f"{finding.path}:{finding.line}: {finding.change} {finding.safety} {finding.message}" for finding in findings
    )
    safe = sum(1 for finding in findings if finding.safety == SAFE)
    out.append(f"{len(findings)} findings: {safe} SAFE, {len(findings) - safe} NEEDS-REVIEW")
    out.extend(f"  {change}: {title} (references/changes.md)" for change, title in changes.items())
    out.extend(f"skipped {item['path']}: {item['reason']}" for item in project.skipped)
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
