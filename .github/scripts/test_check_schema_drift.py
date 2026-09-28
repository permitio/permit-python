"""Contract tests for check_schema_drift.py.

These pin what the workflow relies on: which differences fail and which are only
reported, that the allowlist suppresses exactly what it records and nothing else,
that a run which could not compare exits 2 instead of passing, and that the
generator the script runs is the one `make generate-models` runs. No network and no
generator: each test compares small model modules written as source text.

Run with: python -m pytest .github/scripts/test_check_schema_drift.py
"""

from __future__ import annotations

import http.client
import io
import json
import re
import shlex
import subprocess
import sys
import textwrap
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "check_schema_drift.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).parent))

import check_schema_drift  # noqa: E402
from check_schema_drift import (  # noqa: E402
    GENERATOR_EXCLUDE_NEWER,
    GENERATOR_FLAGS,
    GENERATOR_PACKAGE,
    GENERATOR_PYTHON,
    DriftError,
    apply_allowlist,
    compare,
    fetch_spec,
    load_allowlist,
    parse_models,
    render,
)

HEADER = """\
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Extra, Field, constr
"""

BASE_MODELS = """\
class Color(str, Enum):
    red = 'red'
    blue = 'blue'


class UserRead(BaseModel):
    class Config:
        extra = Extra.allow

    key: str = Field(..., title='Key')
    email: Optional[str] = Field(default=None, title='Email')
    color: Optional[Color] = Field(default='red', title='Color')
    source: str = Field(default=None, alias='from', title='From')
"""


def module(body: str = BASE_MODELS) -> str:
    return HEADER + "\n\n" + textwrap.dedent(body)


def differences(sdk: str, spec: str) -> dict[str, tuple[str, str]]:
    found = compare(parse_models(sdk, "sdk"), parse_models(spec, "spec"))
    return {d.id: (d.sdk, d.spec) for d in found}


def cli(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, check=False)


def run(tmp_path: Path, sdk: str, spec: str, entries: list | None = None, *extra: str):
    sdk_path = tmp_path / "models.py"
    spec_path = tmp_path / "generated.py"
    allowlist = tmp_path / "allowlist.json"
    sdk_path.write_text(sdk)
    spec_path.write_text(spec)
    allowlist.write_text(json.dumps({"entries": entries or []}))
    return cli("--models", sdk_path, "--generated", spec_path, "--allowlist", allowlist, *extra)


# --- CLI contract -------------------------------------------------------------


def test_identical_modules_pass(tmp_path: Path):
    result = run(tmp_path, module(), module())
    assert result.returncode == 0, result.stderr
    assert "matches the API schema" in result.stdout


def test_failing_drift_exits_1_and_names_it(tmp_path: Path):
    spec = module().replace("key: str = Field(..., title='Key')", "key: int = Field(..., title='Key')")
    result = run(tmp_path, module(), spec)
    assert result.returncode == 1
    assert "field_type_changed:UserRead.key" in result.stdout
    assert "field_type_changed:UserRead.key" in result.stderr


def test_informational_drift_does_not_fail(tmp_path: Path):
    spec = module() + "\n\nclass NewThing(BaseModel):\n    name: str\n"
    result = run(tmp_path, module(), spec)
    assert result.returncode == 0
    assert "class_added:NewThing" in result.stdout


def test_github_output_carries_the_counts(tmp_path: Path):
    output = tmp_path / "github_output"
    spec = module().replace("    blue = 'blue'\n", "") + "\n\nclass NewThing(BaseModel):\n    name: str\n"
    result = run(tmp_path, module(), spec, None, "--github-output", str(output))
    assert result.returncode == 1
    assert output.read_text() == "failing=1\ninformational=1\nstale=0\n"


def test_summary_is_written_to_the_given_file_not_stdout(tmp_path: Path):
    summary = tmp_path / "summary.md"
    result = run(tmp_path, module(), module(), None, "--summary", str(summary))
    assert result.returncode == 0
    assert result.stdout == ""
    assert summary.read_text().startswith("## API schema drift")


def test_unparsable_models_exit_2_and_never_read_as_clean(tmp_path: Path):
    result = run(tmp_path, "class Broken(:\n", module())
    assert result.returncode == 2
    assert "did not run" in result.stdout
    assert "matches the API schema" not in result.stdout


def test_missing_generated_file_exits_2(tmp_path: Path):
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text('{"entries": []}')
    models = tmp_path / "models.py"
    models.write_text(module())
    result = cli("--models", models, "--generated", tmp_path / "absent.py", "--allowlist", allowlist)
    assert result.returncode == 2


def test_spec_that_is_not_json_exits_2_before_generating(tmp_path: Path):
    spec = tmp_path / "openapi.json"
    spec.write_text("<html>not a schema</html>")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text('{"entries": []}')
    models = tmp_path / "models.py"
    models.write_text(module())
    result = cli("--models", models, "--spec", spec, "--allowlist", allowlist)
    assert result.returncode == 2
    assert "not valid JSON" in result.stderr


def test_an_unexpected_error_exits_2_not_1(tmp_path: Path):
    # A models file that is not UTF-8 raises UnicodeDecodeError, not DriftError. Exit 1
    # would read as drift with nothing listed.
    summary = tmp_path / "summary.md"
    run(tmp_path, module(), module())
    (tmp_path / "models.py").write_bytes(b"\xff\xfe not utf-8")
    result = cli(
        "--models",
        tmp_path / "models.py",
        "--generated",
        tmp_path / "generated.py",
        "--allowlist",
        tmp_path / "allowlist.json",
        "--summary",
        summary,
    )
    assert result.returncode == 2
    assert "Traceback" in result.stderr
    assert "UnicodeDecodeError" in result.stderr
    assert "The check did not run" in summary.read_text()
    assert "UnicodeDecodeError" in summary.read_text()


SPEC_URL = "https://schema.test/openapi.json"


class FlakyUrlopen:
    """Stands in for urllib.request.urlopen: raises each of `failures` in turn, then serves `body`."""

    def __init__(self, failures: list[Exception], body: bytes = b"{}"):
        self.failures = failures
        self.body = body
        self.requests: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout: float) -> io.BytesIO:
        self.requests.append((url, timeout))
        if self.failures:
            raise self.failures.pop(0)
        return io.BytesIO(self.body)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    pauses: list[float] = []
    monkeypatch.setattr(check_schema_drift.time, "sleep", pauses.append)
    return pauses


def test_a_failed_schema_download_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: list[float]):
    urlopen = FlakyUrlopen(
        [urllib.error.URLError("connection reset"), http.client.IncompleteRead(b"{")], b'{"openapi": "3"}'
    )
    monkeypatch.setattr(check_schema_drift.urllib.request, "urlopen", urlopen)

    spec = fetch_spec(SPEC_URL, tmp_path)

    assert spec.read_text() == '{"openapi": "3"}'
    assert urlopen.requests == [(SPEC_URL, 60)] * 3
    assert sleeps == [5, 10]


def test_a_schema_download_that_keeps_failing_is_a_drift_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
):
    urlopen = FlakyUrlopen([urllib.error.URLError("down") for _ in range(3)])
    monkeypatch.setattr(check_schema_drift.urllib.request, "urlopen", urlopen)

    with pytest.raises(DriftError, match="in 3 attempts: <urlopen error down>"):
        fetch_spec(SPEC_URL, tmp_path)

    assert urlopen.requests == [(SPEC_URL, 60)] * 3
    assert sleeps == [5, 10]


# --- what counts as a difference ----------------------------------------------


def test_formatting_titles_and_field_order_are_not_differences():
    spec = module(
        """\
        class Color(str, Enum):
            blue = "blue"
            red = "red"


        class UserRead(BaseModel):
            class Config:
                extra = Extra.allow

            source: str = Field(None, alias="from", title="Source", description="where from")
            color: Optional[Color] = Field("red")
            email: Optional[str] = Field(
                default=None,
                title="E-mail",
            )
            key: str = Field(..., example="k")
        """
    )
    assert differences(module(), spec) == {}


@pytest.mark.parametrize(
    ("sdk_field", "spec_field", "expected"),
    [
        ("x: str = Field(...)", "x: int = Field(...)", {"field_type_changed:M.x": ("str", "int")}),
        (
            "x: Optional[str] = Field(default=None)",
            "x: Optional[str] = Field(...)",
            {"field_required_changed:M.x": ("optional", "required")},
        ),
        ("x: str = Field(default='a')", "x: str = Field(default='b')", {"field_default_changed:M.x": ("'a'", "'b'")}),
        (
            "x: str = Field(default=None, alias='a')",
            "x: str = Field(default=None, alias='b')",
            {"field_alias_changed:M.x": ("'a'", "'b'")},
        ),
        (
            "x: List[str] = Field(...)",
            "x: List[str] = Field(..., max_items=5)",
            {"field_type_changed:M.x": ("List[str]", "List[str] [max_items=5]")},
        ),
    ],
)
def test_changed_field_is_detected(sdk_field: str, spec_field: str, expected: dict):
    sdk = module(f"class M(BaseModel):\n    {sdk_field}\n")
    spec = module(f"class M(BaseModel):\n    {spec_field}\n")
    assert differences(sdk, spec) == expected


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        ("x: str", "required"),
        ("x: Optional[str]", "optional"),
        ("x: str = Field(...)", "required"),
        ("x: str = Field(default=...)", "required"),
        ("x: Optional[str] = Field(..., title='X')", "required"),
        ("x: str = Field(default=None)", "optional"),
        ("x: str = Field(None)", "optional"),
        ("x: str = 'a'", "optional"),
        ("x: Dict[str, Any] = Field(default_factory=dict)", "optional"),
    ],
)
def test_required_follows_pydantic_1(declaration: str, expected: str):
    shapes = parse_models(module(f"class M(BaseModel):\n    {declaration}\n"), "m")
    assert ("required" if shapes["M"].fields["x"].required else "optional") == expected


def test_field_in_one_module_only():
    sdk = module("class M(BaseModel):\n    a: str\n    gone: str\n")
    spec = module("class M(BaseModel):\n    a: str\n    needed: str\n    maybe: Optional[str] = None\n")
    assert differences(sdk, spec) == {
        "field_removed_from_spec:M.gone": ("required str", "(absent)"),
        "field_added_required:M.needed": ("(absent)", "required str"),
        "field_added_optional:M.maybe": ("(absent)", "optional Optional[str]"),
    }


def test_enum_members_are_compared():
    sdk = module("class E(str, Enum):\n    a = 'a'\n    b = 'b'\n    c = 'c'\n")
    spec = module("class E(str, Enum):\n    a = 'a'\n    b = 'B'\n    d = 'd'\n")
    assert differences(sdk, spec) == {
        "enum_value_changed:E.b": ("'b'", "'B'"),
        "enum_member_removed:E.c": ("'c'", "(absent)"),
        "enum_member_added:E.d": ("(absent)", "'d'"),
    }


def test_class_level_differences():
    sdk = module(
        """\
        class Kind(BaseModel):
            a: str


        class Extra1(BaseModel):
            class Config:
                extra = Extra.forbid

            a: str


        class Gone(BaseModel):
            a: str
        """
    )
    spec = module(
        """\
        class Kind(str, Enum):
            a = 'a'


        class Extra1(BaseModel):
            class Config:
                extra = Extra.allow

            a: str


        class Added(BaseModel):
            a: str
        """
    )
    assert differences(sdk, spec) == {
        "class_kind_changed:Kind": ("model", "enum(str)"),
        "config_extra_changed:Extra1": ("forbid", "allow"),
        "class_removed_from_spec:Gone": ("model", "(absent)"),
        "class_added:Added": ("(absent)", "model"),
    }


def test_inherited_fields_are_compared():
    sdk = module("class Base(BaseModel):\n    a: str\n\n\nclass Child(Base):\n    b: str\n")
    spec = module("class Base(BaseModel):\n    a: str\n\n\nclass Child(BaseModel):\n    a: int\n    b: str\n")
    assert differences(sdk, spec) == {"field_type_changed:Child.a": ("str", "int")}


def test_root_models_compare_their_root_type():
    sdk = module("class R(BaseModel):\n    __root__: List[str] = Field(..., title='R')\n")
    spec = module("class R(BaseModel):\n    __root__: List[int] = Field(..., title='R')\n")
    assert differences(sdk, spec) == {"field_type_changed:R.__root__": ("List[str]", "List[int]")}


def test_a_module_without_classes_is_an_error():
    with pytest.raises(DriftError, match="no classes"):
        parse_models(HEADER, "empty")


def test_the_sdk_models_module_parses_with_its_hand_written_header():
    shapes = parse_models((REPO_ROOT / "permit" / "api" / "models.py").read_text(encoding="utf-8"), "models.py")
    assert len(shapes) > 300
    assert shapes["UserRead"].kind == "model"
    assert shapes["UserRead"].fields["key"].required is True
    assert shapes["AttributeType"].kind == "enum(str)"
    assert "json" in shapes["AttributeType"].members
    # The header binds names inside `if` branches; only top-level classes count.
    assert "EmailStr" not in shapes


# --- allowlist ----------------------------------------------------------------


def entry(entry_id: str, sdk: str, spec: str, reason: str = "known") -> dict:
    return {"id": entry_id, "sdk": sdk, "spec": spec, "reason": reason}


def int_key_spec() -> str:
    return module().replace("key: str = Field(..., title='Key')", "key: int = Field(..., title='Key')")


def test_allowlist_suppresses_an_exact_match(tmp_path: Path):
    result = run(tmp_path, module(), int_key_spec(), [entry("field_type_changed:UserRead.key", "str", "int")])
    assert result.returncode == 0, result.stdout
    assert "| 0 | 0 | 0 | 1 |" in result.stdout


def test_allowlist_does_not_suppress_a_further_change(tmp_path: Path):
    spec = module().replace("key: str = Field(..., title='Key')", "key: float = Field(..., title='Key')")
    result = run(tmp_path, module(), spec, [entry("field_type_changed:UserRead.key", "str", "int")])
    assert result.returncode == 1
    assert "field_type_changed:UserRead.key" in result.stdout


def test_informational_entries_match_on_id_alone(tmp_path: Path):
    # Recorded as a model, now an enum: still the same missing class, so still allowlisted.
    spec = module() + "\n\nclass NewThing(str, Enum):\n    a = 'a'\n"
    result = run(tmp_path, module(), spec, [entry("class_added:NewThing", "(absent)", "model")])
    assert result.returncode == 0
    assert "| 0 | 0 | 0 | 1 |" in result.stdout


def test_stale_entry_fails(tmp_path: Path):
    result = run(tmp_path, module(), module(), [entry("field_type_changed:UserRead.key", "str", "int")])
    assert result.returncode == 1
    assert "Stale allowlist entries" in result.stdout
    assert "stale allowlist entry: field_type_changed:UserRead.key" in result.stderr


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "not valid JSON"),
        (json.dumps({"entries": {}}), '"entries" list'),
        (json.dumps({"entries": [entry("class_added:A", "", "model", reason="")]}), '"reason"'),
        (json.dumps({"entries": [entry("class_added:A", "", "model")] * 2}), "more than once"),
        (json.dumps({"entries": [entry("made_up_kind:A", "", "")]}), "unknown kind"),
    ],
)
def test_invalid_allowlist_exits_2(tmp_path: Path, content: str, message: str):
    (tmp_path / "models.py").write_text(module())
    (tmp_path / "allowlist.json").write_text(content)
    result = cli(
        "--models",
        tmp_path / "models.py",
        "--generated",
        tmp_path / "models.py",
        "--allowlist",
        tmp_path / "allowlist.json",
    )
    assert result.returncode == 2
    assert message in result.stderr


def test_the_committed_allowlist_is_valid_and_every_entry_has_a_reason():
    entries = load_allowlist(Path(__file__).parent / "schema_drift_allowlist.json")
    assert entries
    assert all(len(e.reason.strip()) > 10 for e in entries)


# --- report -------------------------------------------------------------------


def test_pipes_and_backticks_in_schema_text_cannot_break_the_table():
    sdk = module("class M(BaseModel):\n    x: constr(regex='^a$')\n")
    spec = module("class M(BaseModel):\n    x: constr(regex='^a|`b`$')\n")
    result = apply_allowlist(compare(parse_models(sdk, "sdk"), parse_models(spec, "spec")), [])
    report = render(result, "test")
    row = next(line for line in report.splitlines() if "field_type_changed:M.x" in line)
    assert "a\\|'b'$" in row
    assert row.count("`") == 6


# --- the generator is the one make generate-models runs -----------------------


def test_generator_matches_the_makefile():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = re.search(r"^generate-models:\n((?:\t.*\n?)+)", makefile, re.MULTILINE)
    assert recipe, "the Makefile has no generate-models recipe"
    words = shlex.split(recipe.group(1).replace("\\\n", " "))
    assert words[:7] == [
        "uvx",
        "--python",
        GENERATOR_PYTHON,
        "--exclude-newer",
        GENERATOR_EXCLUDE_NEWER,
        "--from",
        GENERATOR_PACKAGE.replace("==", "[http]=="),
    ]
    assert words[7] == "datamodel-codegen"
    flags = words[8:]
    # --url and --output name the source and the target; everything else must match.
    for option in ("--url", "--output"):
        index = flags.index(option)
        del flags[index : index + 2]
    assert tuple(flags) == GENERATOR_FLAGS
