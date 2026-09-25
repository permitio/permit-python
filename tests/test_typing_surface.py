"""Checks on the SDK's surface as type checkers see it.

permit ships py.typed, so a user's type checker analyzes every call into the SDK. These
tests keep that surface free of false errors and keep the generated stub for the blocking
client in step with the async classes it mirrors.
"""

import ast
import difflib
import importlib
import importlib.util
import pkgutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import permit
from permit.utils.sync import SYNC_WRAPPER_MARKER, SyncClass, iscoroutine_func

REPO_ROOT = Path(__file__).resolve().parents[1]
TYPE_CHECK_DIR = REPO_ROOT / "tests" / "type_check"
STUB = REPO_ROOT / "permit" / "_sync_types.pyi"


def load_stub_generator() -> ModuleType:
    path = REPO_ROOT / "scripts" / "generate_sync_stubs.py"
    spec = importlib.util.spec_from_file_location("generate_sync_stubs", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_consumer_code_type_checks_without_errors(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(TYPE_CHECK_DIR / "mypy.ini"),
            "--cache-dir",
            str(tmp_path),
            str(TYPE_CHECK_DIR / "consumer.py"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_sync_stub_matches_the_async_classes():
    generator = load_stub_generator()

    expected = generator.render_stub()
    committed = STUB.read_text()

    diff = "".join(
        difflib.unified_diff(
            committed.splitlines(keepends=True), expected.splitlines(keepends=True), "committed", "generated"
        )
    )
    assert not diff, f"permit/_sync_types.pyi is out of date. Run `make generate-sync-stubs`.\n{diff}"


def runtime_sync_classes() -> dict[str, type]:
    """Every class declared with ``metaclass=SyncClass``, keyed by qualified name."""
    found: dict[str, type] = {}
    for info in pkgutil.walk_packages(permit.__path__, "permit."):
        for value in vars(importlib.import_module(info.name)).values():
            if (
                isinstance(value, SyncClass)
                and value.__module__ == info.name
                and not any(isinstance(base, SyncClass) for base in value.__bases__)
            ):
                found[f"{value.__module__}.{value.__qualname__}"] = value
    return found


def stub_plain_methods() -> dict[str, set[str]]:
    """Public, undecorated ``def`` names of every class in the stub."""
    classes = {}
    for node in ast.parse(STUB.read_text()).body:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = {
                member.name
                for member in node.body
                if isinstance(member, ast.FunctionDef) and not member.name.startswith("_") and not member.decorator_list
            }
    return classes


def test_sync_stub_declares_exactly_the_methods_sync_class_makes_blocking():
    generator = load_stub_generator()
    stub = stub_plain_methods()
    runtime = runtime_sync_classes()

    assert sorted(stub) == sorted(generator.stub_name(cls) for cls in runtime.values())
    for sync_cls in runtime.values():
        (async_cls,) = sync_cls.__bases__
        # SyncClass's own rule: every public attribute whose call returns an awaitable.
        converted = {
            name for name in dir(async_cls) if not name.startswith("_") and iscoroutine_func(getattr(async_cls, name))
        }
        assert stub[generator.stub_name(sync_cls)] == converted, sync_cls
        for name in converted:
            method = getattr(sync_cls, name)
            assert getattr(method, SYNC_WRAPPER_MARKER, False), f"{sync_cls.__name__}.{name}"
            assert not iscoroutine_func(method), f"{sync_cls.__name__}.{name}"
