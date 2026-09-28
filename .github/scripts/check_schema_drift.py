#!/usr/bin/env python3
"""Compare permit/api/models.py with models generated from the public API schema.

permit/api/models.py is generated from https://api.permit.io/v2/openapi.json and
then edited by hand in a few places. Nothing regenerates it on a schedule, so the
API schema can move on without the SDK noticing. This script generates models from
the current schema with the same generator and flags as `make generate-models`,
then compares the two modules structurally: it parses both with `ast` and compares
classes, fields, field types, required vs optional, defaults, aliases, the model
`Config.extra` setting and enum members. Formatting, field order, titles,
descriptions and examples are ignored. Neither module is imported.

What fails and what does not:

* Failing kinds are differences that make the SDK send something the API rejects,
  or reject or misparse something the API sends: a changed field type, a field that
  became required or optional, a changed default or alias, a field or class the
  schema dropped, a new required field (requests without it are rejected), a changed
  `extra` setting, and any enum change (a member the schema added makes the SDK fail
  to parse a response that carries it).
* Informational kinds only mean the SDK lacks something the API offers: a class the
  schema added, or a new optional field. They are listed but never fail the check.

Differences that are known and intended live in an allowlist, each with a one-line
reason, so the check reports only new drift. A failing-kind entry matches only when
its id and both recorded values match, so a further change to an allowlisted
difference is reported as new. An informational-kind entry matches on its id alone:
it never fails, and pinning its values would only fail the check when the schema
changes something the SDK does not model. An entry that matches nothing is stale
and fails the check, so the allowlist shrinks when the models are regenerated.

Contract (the workflow depends on it):

* Exit 0: no new failing difference and no stale allowlist entry.
* Exit 1: at least one new failing difference or stale allowlist entry.
* Exit 2: the comparison did not run -- the schema could not be fetched (a failed
  download is retried twice), the generator failed, a models file did not parse, the
  allowlist is invalid, or any other error stopped it. A run that did not compare is
  never reported as clean.
* The markdown report goes to --summary (default stdout), diagnostics to stderr, and
  --github-output receives `failing=`, `informational=` and `stale=` counts.

Stdlib only: this runs on a bare actions/setup-python. Generating needs `uvx` on PATH.
"""

from __future__ import annotations

import argparse
import ast
import http.client
import json
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SPEC = "https://api.permit.io/v2/openapi.json"

# The generator release that produced permit/api/models.py (0.33.0 was current on
# its 2025-09-17 timestamp). --exclude-newer freezes the generator's own
# dependencies and formatters at the end of that day (UTC), whose pydantic-core has
# no Python 3.14 wheel, hence --python 3.11. The Makefile's generate-models target
# uses the same values; test_check_schema_drift.py keeps the two in step.
GENERATOR_PYTHON = "3.11"
GENERATOR_EXCLUDE_NEWER = "2025-09-18T00:00:00Z"
GENERATOR_PACKAGE = "datamodel-code-generator==0.33.0"
GENERATOR_FLAGS = (
    "--input-file-type",
    "openapi",
    "--output-model-type",
    "pydantic.BaseModel",
    "--allow-extra-fields",
    "--enum-field-as-literal",
    "one",
    "--use-one-literal-as-default",
    "--use-subclass-enum",
    "--use-default-kwarg",
)

FETCH_TIMEOUT_S = 60
# A first try and two retries, 5s and then 10s apart.
FETCH_ATTEMPTS = 3
FETCH_BACKOFF_S = 5
GENERATE_TIMEOUT_S = 600

FAILING_KINDS = frozenset(
    {
        "class_kind_changed",
        "class_removed_from_spec",
        "config_extra_changed",
        "enum_member_added",
        "enum_member_removed",
        "enum_value_changed",
        "field_added_required",
        "field_alias_changed",
        "field_default_changed",
        "field_removed_from_spec",
        "field_required_changed",
        "field_type_changed",
    }
)
INFORMATIONAL_KINDS = frozenset({"class_added", "field_added_optional"})

ABSENT = "(absent)"

# Field(...) keywords that do not change what the SDK sends or accepts.
DOC_KEYWORDS = frozenset({"title", "description", "example", "examples"})


class DriftError(Exception):
    """The comparison could not run. Maps to exit code 2."""


@dataclass(frozen=True)
class FieldShape:
    type: str
    required: bool
    default: str | None
    alias: str | None


@dataclass(frozen=True)
class ClassShape:
    kind: str
    fields: dict[str, FieldShape]
    extra: str
    members: dict[str, str]


@dataclass(frozen=True)
class Difference:
    kind: str
    cls: str
    name: str
    sdk: str
    spec: str

    @property
    def id(self) -> str:
        target = f"{self.cls}.{self.name}" if self.name else self.cls
        return f"{self.kind}:{target}"

    @property
    def failing(self) -> bool:
        return self.kind in FAILING_KINDS


@dataclass(frozen=True)
class AllowlistEntry:
    id: str
    sdk: str
    spec: str
    reason: str


@dataclass
class Result:
    new: list[Difference]
    allowlisted: list[Difference]
    stale: list[AllowlistEntry]

    @property
    def failing(self) -> list[Difference]:
        return [d for d in self.new if d.failing]

    @property
    def informational(self) -> list[Difference]:
        return [d for d in self.new if not d.failing]

    @property
    def exit_code(self) -> int:
        return 1 if self.failing or self.stale else 0


# --- parsing ------------------------------------------------------------------


def _base_names(node: ast.ClassDef) -> list[str]:
    return [ast.unparse(base).rsplit(".", 1)[-1] for base in node.bases]


def _is_optional(annotation: ast.expr) -> bool:
    """Whether pydantic 1 treats a field with this annotation and no value as optional."""
    text = ast.unparse(annotation)
    if text.startswith("Optional["):
        return True
    if isinstance(annotation, ast.Subscript) and ast.unparse(annotation.value) == "Union":
        members = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        return any(ast.unparse(member) == "None" for member in members)
    return False


def _is_ellipsis(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is Ellipsis


def _field_shape(node: ast.AnnAssign) -> FieldShape:
    """Read one annotated class attribute the way pydantic 1 reads a field."""
    annotation = node.annotation
    value = node.value
    extras: list[str] = []
    alias: str | None = None
    default_node: ast.expr | None = None
    has_default = False
    if isinstance(value, ast.Call) and ast.unparse(value.func).rsplit(".", 1)[-1] == "Field":
        if value.args:
            default_node, has_default = value.args[0], True
        for keyword in value.keywords:
            if keyword.arg in ("default", "default_factory"):
                default_node, has_default = keyword.value, True
            elif keyword.arg == "alias":
                alias = ast.unparse(keyword.value)
            elif keyword.arg not in DOC_KEYWORDS:
                extras.append(f"{keyword.arg}={ast.unparse(keyword.value)}")
    elif value is not None:
        default_node, has_default = value, True

    if has_default and default_node is not None and _is_ellipsis(default_node):
        required = True
        default = None
    elif has_default and default_node is not None:
        required = False
        default = ast.unparse(default_node)
        default = None if default == "None" else default
    else:
        required = not _is_optional(annotation)
        default = None

    type_text = ast.unparse(annotation)
    if extras:
        type_text += f" [{', '.join(sorted(extras))}]"
    return FieldShape(type=type_text, required=required, default=default, alias=alias)


def _config_extra(node: ast.ClassDef) -> str | None:
    for item in node.body:
        if isinstance(item, ast.ClassDef) and item.name == "Config":
            for statement in item.body:
                if isinstance(statement, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "extra" for t in statement.targets
                ):
                    return ast.unparse(statement.value).rsplit(".", 1)[-1]
    return None


def parse_models(source: str, label: str) -> dict[str, ClassShape]:
    """Return the shape of every top-level class in a generated models module.

    Args:
        source: The module's source text.
        label: A name for the module, used in error messages.

    Returns:
        Class name to shape. Model fields include those inherited from other classes
        in the same module.

    Raises:
        DriftError: If the source does not parse or declares no classes.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise DriftError(f"{label} does not parse: {exc}") from exc
    nodes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    if not nodes:
        raise DriftError(f"{label} declares no classes, so there is nothing to compare")

    resolved: dict[str, ClassShape] = {}

    def resolve(name: str, chain: tuple[str, ...]) -> ClassShape:
        if name in resolved:
            return resolved[name]
        if name in chain:
            raise DriftError(f"{label}: class {name} inherits from itself")
        node = nodes[name]
        bases = _base_names(node)
        local_bases = [resolve(base, (*chain, name)) for base in bases if base in nodes]
        if "Enum" in bases:
            kind = "enum(str)" if "str" in bases else "enum"
        elif "BaseModel" in bases or any(base.kind == "model" for base in local_bases):
            kind = "model"
        else:
            kind = "other"

        fields: dict[str, FieldShape] = {}
        members: dict[str, str] = {}
        extra = "default"
        # Reversed so the first base wins, as it does in Python's method resolution order.
        for base in reversed(local_bases):
            fields.update(base.fields)
            members.update(base.members)
            extra = base.extra if base.extra != "default" else extra
        own_extra = _config_extra(node)
        if own_extra is not None:
            extra = own_extra
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields[item.target.id] = _field_shape(item)
            elif kind.startswith("enum") and isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        members[target.id] = ast.unparse(item.value)
        shape = ClassShape(kind=kind, fields=fields, extra=extra, members=members)
        resolved[name] = shape
        return shape

    return {name: resolve(name, ()) for name in nodes}


# --- comparison ---------------------------------------------------------------


def _describe_field(shape: FieldShape) -> str:
    return f"{'required' if shape.required else 'optional'} {shape.type}"


def compare(sdk: dict[str, ClassShape], spec: dict[str, ClassShape]) -> list[Difference]:
    """List every structural difference between the SDK's models and the schema's.

    Args:
        sdk: Shapes parsed from permit/api/models.py.
        spec: Shapes parsed from the models generated from the API schema.

    Returns:
        The differences, sorted by id.
    """
    out: list[Difference] = []
    for name in sorted(set(sdk) | set(spec)):
        if name not in sdk:
            out.append(Difference("class_added", name, "", ABSENT, spec[name].kind))
            continue
        if name not in spec:
            out.append(Difference("class_removed_from_spec", name, "", sdk[name].kind, ABSENT))
            continue
        ours, theirs = sdk[name], spec[name]
        if ours.kind != theirs.kind:
            out.append(Difference("class_kind_changed", name, "", ours.kind, theirs.kind))
            continue
        if ours.kind.startswith("enum"):
            out.extend(_compare_members(name, ours.members, theirs.members))
        elif ours.kind == "model":
            if ours.extra != theirs.extra:
                out.append(Difference("config_extra_changed", name, "", ours.extra, theirs.extra))
            out.extend(_compare_fields(name, ours.fields, theirs.fields))
    return sorted(out, key=lambda d: d.id)


def _compare_members(cls: str, ours: dict[str, str], theirs: dict[str, str]) -> list[Difference]:
    out = []
    for member in sorted(set(ours) | set(theirs)):
        if member not in ours:
            out.append(Difference("enum_member_added", cls, member, ABSENT, theirs[member]))
        elif member not in theirs:
            out.append(Difference("enum_member_removed", cls, member, ours[member], ABSENT))
        elif ours[member] != theirs[member]:
            out.append(Difference("enum_value_changed", cls, member, ours[member], theirs[member]))
    return out


def _compare_fields(cls: str, ours: dict[str, FieldShape], theirs: dict[str, FieldShape]) -> list[Difference]:
    out = []
    for field in sorted(set(ours) | set(theirs)):
        if field not in ours:
            kind = "field_added_required" if theirs[field].required else "field_added_optional"
            out.append(Difference(kind, cls, field, ABSENT, _describe_field(theirs[field])))
            continue
        if field not in theirs:
            out.append(Difference("field_removed_from_spec", cls, field, _describe_field(ours[field]), ABSENT))
            continue
        mine, spec = ours[field], theirs[field]
        if mine.type != spec.type:
            out.append(Difference("field_type_changed", cls, field, mine.type, spec.type))
        if mine.required != spec.required:
            out.append(
                Difference(
                    "field_required_changed",
                    cls,
                    field,
                    "required" if mine.required else "optional",
                    "required" if spec.required else "optional",
                )
            )
        elif mine.default != spec.default:
            out.append(Difference("field_default_changed", cls, field, str(mine.default), str(spec.default)))
        if mine.alias != spec.alias:
            out.append(Difference("field_alias_changed", cls, field, str(mine.alias), str(spec.alias)))
    return out


# --- allowlist ----------------------------------------------------------------


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    """Read and validate the allowlist.

    Raises:
        DriftError: If the file is missing, is not valid JSON, or has an entry
            without an id or reason, with a duplicate id, or with an unknown kind.
    """
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DriftError(f"could not read the allowlist {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DriftError(f"the allowlist {path} is not valid JSON: {exc}") from exc
    raw_entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(raw_entries, list):
        raise DriftError(f'the allowlist {path} must be an object with an "entries" list')

    entries: list[AllowlistEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise DriftError(f"allowlist entry {index} is not an object")
        values = {key: raw.get(key) for key in ("id", "sdk", "spec", "reason")}
        for key, value in values.items():
            if not isinstance(value, str) or (key in ("id", "reason") and not value.strip()):
                raise DriftError(f'allowlist entry {index} needs a non-empty string "{key}"')
        entry_id = str(values["id"])
        kind = entry_id.split(":", 1)[0]
        if kind not in FAILING_KINDS | INFORMATIONAL_KINDS:
            raise DriftError(f"allowlist entry {entry_id} has an unknown kind {kind!r}")
        if entry_id in seen:
            raise DriftError(f"allowlist entry {entry_id} appears more than once")
        seen.add(entry_id)
        entries.append(AllowlistEntry(entry_id, str(values["sdk"]), str(values["spec"]), str(values["reason"])))
    return entries


def apply_allowlist(differences: list[Difference], entries: list[AllowlistEntry]) -> Result:
    """Split differences into new and allowlisted, and find stale entries."""
    by_id = {entry.id: entry for entry in entries}
    matched: set[str] = set()
    new: list[Difference] = []
    allowlisted: list[Difference] = []
    for difference in differences:
        entry = by_id.get(difference.id)
        if entry is not None and (
            not difference.failing or (entry.sdk == difference.sdk and entry.spec == difference.spec)
        ):
            matched.add(entry.id)
            allowlisted.append(difference)
        else:
            new.append(difference)
    stale = [entry for entry in entries if entry.id not in matched]
    return Result(new=new, allowlisted=allowlisted, stale=stale)


# --- report -------------------------------------------------------------------


def _cell(text: str) -> str:
    """Make external text safe inside a markdown table cell or inline code."""
    return " ".join(str(text).split()).replace("|", "\\|").replace("`", "'")


def render(result: Result, compared_with: str) -> str:
    """Render the markdown report.

    Args:
        result: The comparison after the allowlist was applied.
        compared_with: What permit/api/models.py was compared with, already markdown.

    Returns:
        The report, ending with a newline.
    """
    failing, informational = result.failing, result.informational
    out = ["## API schema drift", ""]
    if result.exit_code == 0:
        out.append(
            ":white_check_mark: **permit/api/models.py matches the API schema** apart from allowlisted differences."
        )
    else:
        out.append(":x: **permit/api/models.py has drifted from the API schema.**")
    out += [
        "",
        f"_Compared with {compared_with}._",
        "",
        "| New failing | New informational | Stale allowlist entries | Allowlisted |",
        "|---|---|---|---|",
        f"| {len(failing)} | {len(informational)} | {len(result.stale)} | {len(result.allowlisted)} |",
        "",
    ]
    if failing:
        out += ["### New failing differences", "", "| Difference | SDK | API schema |", "|---|---|---|"]
        out += [f"| `{_cell(d.id)}` | `{_cell(d.sdk)}` | `{_cell(d.spec)}` |" for d in failing]
        out.append("")
    if informational:
        out += ["### New informational differences", "", "These do not fail the check.", ""]
        out += [f"- `{_cell(d.id)}`: `{_cell(d.spec)}`" for d in informational]
        out.append("")
    if result.stale:
        out += ["### Stale allowlist entries", "", "These match no current difference. Remove them.", ""]
        out += [f"- `{_cell(entry.id)}`" for entry in result.stale]
        out.append("")
    if result.new or result.stale:
        out.append(
            "To resolve: regenerate the models (`make generate-models`, see the comment above generate-models in "
            "the Makefile), or add each intended difference to `.github/scripts/schema_drift_allowlist.json` "
            "with a one-line reason."
        )
        out.append("")
    return "\n".join(out)


# --- inputs -------------------------------------------------------------------


def _download(url: str, target: Path) -> None:
    """Download url to target, retrying a failed attempt after a growing pause."""
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_S) as response:
                target.write_bytes(response.read())
            return
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
            if attempt == FETCH_ATTEMPTS:
                raise DriftError(
                    f"could not fetch the API schema from {url} in {FETCH_ATTEMPTS} attempts: {exc}"
                ) from exc
            pause = FETCH_BACKOFF_S * attempt
            print(f"fetching the API schema failed ({exc}); retrying in {pause}s", file=sys.stderr)
            time.sleep(pause)


def fetch_spec(source: str, workdir: Path) -> Path:
    """Return a local path to the API schema, downloading it when given a URL."""
    if source.startswith(("http://", "https://")):
        target = workdir / "openapi.json"
        _download(source, target)
    else:
        target = Path(source)
    try:
        json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DriftError(f"could not read the API schema at {target}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DriftError(f"the API schema from {source} is not valid JSON: {exc}") from exc
    return target


def generator_command(spec: Path, output: Path) -> list[str]:
    return [
        "uvx",
        "--python",
        GENERATOR_PYTHON,
        "--exclude-newer",
        GENERATOR_EXCLUDE_NEWER,
        "--from",
        GENERATOR_PACKAGE,
        "datamodel-codegen",
        "--input",
        str(spec),
        "--output",
        str(output),
        *GENERATOR_FLAGS,
    ]


def generate(spec: Path, workdir: Path) -> Path:
    """Run the pinned generator on the schema and return the generated module's path."""
    output = workdir / "generated_models.py"
    try:
        completed = subprocess.run(
            generator_command(spec, output),
            capture_output=True,
            text=True,
            timeout=GENERATE_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DriftError("uvx is not on PATH; it runs the pinned model generator") from exc
    except subprocess.TimeoutExpired as exc:
        raise DriftError(f"the model generator did not finish within {GENERATE_TIMEOUT_S}s") from exc
    if completed.returncode != 0 or not output.is_file():
        tail = "\n".join((completed.stderr or completed.stdout).strip().splitlines()[-20:])
        raise DriftError(f"the model generator failed (exit {completed.returncode}):\n{tail}")
    return output


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DriftError(f"could not read {label} at {path}: {exc}") from exc


def run(args: argparse.Namespace) -> Result:
    """Load both model modules and the allowlist, and compare them."""
    entries = load_allowlist(Path(args.allowlist))
    sdk = parse_models(_read(Path(args.models), "the SDK models"), str(args.models))
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        generated = Path(args.generated) if args.generated else generate(fetch_spec(args.spec, workdir), workdir)
        spec = parse_models(_read(generated, "the generated models"), "the models generated from the API schema")
    return apply_allowlist(compare(sdk, spec), entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--models", required=True, help="the SDK's models module (permit/api/models.py)")
    parser.add_argument("--allowlist", required=True, help="JSON allowlist of known differences")
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="API schema URL or path (default: %(default)s)")
    parser.add_argument("--generated", help="compare this generated module instead of running the generator")
    parser.add_argument("--summary", help="write the markdown report here instead of stdout")
    parser.add_argument("--github-output", help="append failing=, informational= and stale= counts here")
    args = parser.parse_args(argv)

    if args.generated:
        compared_with = f"`{_cell(args.generated)}`"
    else:
        compared_with = f"models generated from `{_cell(args.spec)}` by {GENERATOR_PACKAGE}"
    try:
        result = run(args)
    except DriftError as exc:
        print(f"schema drift check could not run: {exc}", file=sys.stderr)
        _emit(_did_not_run_report(str(exc)), args.summary)
        return 2
    # Any other error, such as a file that is not UTF-8, is also a run that did not
    # compare, not drift: exit 1 would read as drift with nothing listed.
    except Exception as exc:  # noqa: BLE001 - mapped to exit 2 with its traceback on stderr
        traceback.print_exc()
        _emit(_did_not_run_report(f"{type(exc).__name__}: {exc}"), args.summary)
        return 2

    _emit(render(result, compared_with), args.summary)
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as handle:
            handle.write(
                f"failing={len(result.failing)}\ninformational={len(result.informational)}\n"
                f"stale={len(result.stale)}\n"
            )
    for difference in result.failing:
        print(f"new drift: {difference.id}: SDK {difference.sdk!r}, API schema {difference.spec!r}", file=sys.stderr)
    for entry in result.stale:
        print(f"stale allowlist entry: {entry.id}", file=sys.stderr)
    return result.exit_code


def _did_not_run_report(reason: str) -> str:
    first_line = (reason.splitlines() or [""])[0]
    return (
        "## API schema drift\n\n:warning: **The check did not run**, so this is not a clean result.\n\n"
        f"`{_cell(first_line)}`\n"
    )


def _emit(report: str, summary: str | None) -> None:
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(report)
    else:
        print(report)


if __name__ == "__main__":
    sys.exit(main())
