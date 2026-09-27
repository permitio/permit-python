"""Offline tests for MIGRATION.md and the permit-python-3-migration skill.

The scanner is loaded from the skill folder, the way a customer runs it, and pointed at the
sample apps in tests/migration_fixtures: v2_app is written against permit 2.x, v3_app is the
same app migrated to 3.0.0. The docs are checked against each other, against the scanner and
against permit/api/deprecated.py, so a change to one that the others miss fails here.
"""

import ast
import hashlib
import importlib
import importlib.util
import inspect
import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Set, Tuple

import pytest

from permit import Permit, PermitConfig
from permit.api.models import AuditLogObjectsModel, DetailedAuditLogModel

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "permit-python-3-migration"
SCANNER = SKILL_DIR / "scripts" / "scan.py"
CHANGES = SKILL_DIR / "references" / "changes.md"
MIGRATION = REPO_ROOT / "MIGRATION.md"
FIXTURES = REPO_ROOT / "tests" / "migration_fixtures"
SAFE = "SAFE"
REVIEW = "NEEDS-REVIEW"

Row = Tuple[str, int, str, str]


def load_scanner() -> ModuleType:
    """Import scan.py without writing a __pycache__ into the folder customers copy."""
    spec = importlib.util.spec_from_file_location("permit_migration_scan", SCANNER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = dont_write_bytecode
    return module


scan = load_scanner()


def findings(root: Path) -> List[Row]:
    return [(item.path, item.line, item.change, item.safety) for item in scan.Project(root).scan()]


def write(root: Path, files: Dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"))
    return root


# ---------------------------------------------------------------------------
# The sample apps
# ---------------------------------------------------------------------------

V2_FINDINGS: Set[Row] = {
    (".gitlab-ci.yml", 2, "C1", REVIEW),
    (".gitlab-ci.yml", 5, "C1", REVIEW),
    (".python-version", 1, "C1", REVIEW),
    ("Dockerfile", 1, "C1", REVIEW),
    ("app/aliases.py", 3, "T1", SAFE),
    ("app/aliases.py", 18, "D2", SAFE),
    ("app/aliases.py", 29, "A2", REVIEW),
    ("app/aliases.py", 33, "D2", REVIEW),
    ("app/aliases.py", 37, "A2", REVIEW),
    ("app/aliases.py", 41, "A6", SAFE),
    ("app/aliases.py", 45, "A3", SAFE),
    ("app/async_app.py", 5, "C2", SAFE),
    ("app/async_app.py", 7, "A6", SAFE),
    ("app/async_app.py", 8, "A3", SAFE),
    ("app/async_app.py", 9, "A3", SAFE),
    ("app/async_app.py", 9, "A3", REVIEW),
    ("app/async_app.py", 16, "D2", SAFE),
    ("app/async_app.py", 17, "T2", SAFE),
    ("app/async_app.py", 21, "D2", SAFE),
    ("app/async_app.py", 25, "D2", SAFE),
    ("app/async_app.py", 29, "D2", SAFE),
    ("app/async_app.py", 33, "W1", REVIEW),
    ("app/async_app.py", 34, "W1", REVIEW),
    ("app/async_app.py", 35, "W1", REVIEW),
    ("app/async_app.py", 39, "A1", REVIEW),
    ("app/models.py", 5, "A4", REVIEW),
    ("app/models.py", 6, "A3", REVIEW),
    ("app/models.py", 10, "W5", REVIEW),
    ("app/models.py", 15, "A4", REVIEW),
    ("app/models.py", 24, "T2", SAFE),
    ("app/models.py", 28, "T2", REVIEW),
    ("app/models.py", 32, "A5", REVIEW),
    ("app/models.py", 44, "T2", SAFE),
    ("app/sync_app.py", 8, "A3", REVIEW),
    ("app/sync_app.py", 19, "A3", REVIEW),
    ("app/sync_app.py", 23, "A2", REVIEW),
    ("app/sync_app.py", 28, "A2", REVIEW),
    ("app/sync_app.py", 32, "A2", SAFE),
    ("app/sync_app.py", 36, "D2", SAFE),
    ("app/sync_app.py", 40, "D2", SAFE),
    ("pyproject.toml", 4, "C1", REVIEW),
    ("pyproject.toml", 6, "P1", SAFE),
    ("pyproject.toml", 7, "D1", REVIEW),
    ("pyproject.toml", 8, "C3", SAFE),
    ("pyproject.toml", 12, "C1", REVIEW),
    ("pyproject.toml", 15, "T1", SAFE),
    ("pyproject.toml", 19, "D1", REVIEW),
    ("requirements.txt", 1, "P1", SAFE),
    ("requirements.txt", 2, "C3", SAFE),
    ("requirements.txt", 3, "C3", SAFE),
}


def test_git_tracks_every_fixture_file():
    """A fixture file that git ignores is missing from every clone, so the tests below fail in CI."""
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    files = [path.relative_to(REPO_ROOT).as_posix() for path in FIXTURES.rglob("*") if path.is_file()]

    result = subprocess.run(["git", "check-ignore", *files], cwd=REPO_ROOT, capture_output=True, text=True, check=False)

    assert result.returncode == 1, f"git ignores these fixture files:\n{result.stdout}{result.stderr}"


def test_scanner_finds_every_site_in_the_2x_app():
    found = findings(FIXTURES / "v2_app")

    assert len(found) == len(set(found)), "a site was reported twice"
    assert set(found) == V2_FINDINGS


def test_scanner_reports_nothing_in_the_migrated_app():
    project = scan.Project(FIXTURES / "v3_app")

    assert project.scan() == []
    assert project.skipped == []


def test_safe_edits_name_the_replacement():
    messages = {(item.path, item.line): item.message for item in scan.Project(FIXTURES / "v2_app").scan()}

    assert "use self.permit.api.tenants.get(...)" in messages[("app/aliases.py", 18)]
    assert "rename tenant= to tenant_data=" in messages[("app/async_app.py", 21)]
    assert (
        'permit.api.users.assign_role({"user": user, "role": role, "tenant": tenant})'
        in messages[("app/async_app.py", 25)]
    )
    assert "use api.resources.get(...)" in messages[("app/async_app.py", 29)]
    assert "use client.elements.login_as(...)" in messages[("app/sync_app.py", 40)]
    assert "call the method directly" in messages[("app/sync_app.py", 32)]
    assert "switch it to the async permit.Permit" in messages[("app/sync_app.py", 23)]


def test_json_report_matches_the_findings_and_names_the_changes():
    result = subprocess.run(
        [sys.executable, str(SCANNER), str(FIXTURES / "v2_app"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    rows = {(item["path"], item["line"], item["change"], item["safety"]) for item in report["findings"]}
    assert rows == V2_FINDINGS
    assert set(report["changes"]) == {row[2] for row in V2_FINDINGS}
    assert report["summary"]["uses_sync_client"] is True
    assert report["summary"]["httpx_declared"] is False
    assert report["summary"]["permit_requirements"] == [
        "pyproject.toml:6: permit>=2.8,<3",
        "requirements.txt:1: permit==2.8.3",
    ]


# ---------------------------------------------------------------------------
# Aliases and receivers
# ---------------------------------------------------------------------------


def test_scanner_follows_every_way_of_importing_the_clients(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            import asyncio

            import permit.sync
            import permit.sync as ps
            from permit import Permit as AsyncPermit
            from permit import sync as permit_sync
            from permit.sync import Permit as Blocking

            a = permit.sync.Permit(token="t")
            b = ps.Permit(token="t")
            c = permit_sync.Permit(token="t")
            d = Blocking(token="t")
            e = AsyncPermit(token="t")
            f: "Blocking" = make()


            def run(g: Blocking, h: AsyncPermit) -> None:
                asyncio.run(a.authorized_users("read", "doc"))
                asyncio.run(b.filter_objects("u", "read", {}, []))
                asyncio.run(c.get_user_permissions("u"))
                asyncio.run(d.authorized_users("read", "doc"))
                asyncio.run(e.authorized_users("read", "doc"))
                asyncio.run(f.authorized_users("read", "doc"))
                asyncio.run(g.authorized_users("read", "doc"))
                asyncio.run(h.authorized_users("read", "doc"))
            """
        },
    )

    # SAFE only on a traced blocking client: every one, however it was imported or annotated,
    # and neither async one.
    assert findings(tmp_path) == [("app.py", line, "A2", SAFE) for line in (18, 19, 20, 21, 23, 24)]


def test_awaiting_a_blocking_method_is_a_question_only_in_async_code(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            import asyncio
            from asyncio import gather, run as run_now

            from permit import Permit
            from permit.sync import Permit as SyncPermit

            client = SyncPermit(token="t")
            async_client = Permit(token="t")
            loop = asyncio.new_event_loop()


            def main():
                asyncio.run(client.filter_objects("u", "read", {}, []))
                run_now(client.authorized_users("read", "doc"))
                loop.run_until_complete(client.get_user_permissions("u"))
                asyncio.run(async_client.filter_objects("u", "read", {}, []))


            async def handler():
                await client.authorized_users("read", "doc")
                await gather(client.get_user_permissions("u"))
                await async_client.authorized_users("read", "doc")
            """
        },
    )
    found = scan.Project(tmp_path).scan()

    # Run to completion from sync code, the call can simply be made directly. Inside a
    # coroutine, a blocking call blocks the event loop: the async client may be the better edit.
    assert [(item.line, item.change, item.safety) for item in found] == [
        (13, "A2", SAFE),
        (14, "A2", SAFE),
        (15, "A2", SAFE),
        (20, "A2", REVIEW),
        (21, "A2", REVIEW),
    ]
    assert "call the method directly" in found[0].message
    for item in found[3:]:
        assert "switch it to the async permit.Permit" in item.message
        assert "(recommended)" in item.message


def test_async_mocks_of_the_three_methods_need_review(tmp_path: Path):
    write(
        tmp_path,
        {
            "test_app.py": """
            from unittest import mock
            from unittest.mock import AsyncMock, patch

            from permit import Permit
            from permit.sync import Permit as SyncPermit

            client = SyncPermit(token="t")
            async_client = Permit(token="t")


            def test_doubles(monkeypatch, mocker):
                monkeypatch.setattr(client, "authorized_users", AsyncMock(return_value=[]))
                client.get_user_permissions = AsyncMock(return_value={})
                with patch("app.client.filter_objects", new_callable=AsyncMock):
                    pass
                with patch.object(SyncPermit, "authorized_users", new_callable=mock.AsyncMock):
                    pass
                monkeypatch.setattr(async_client, "authorized_users", AsyncMock(return_value=[]))
                async_client.filter_objects = AsyncMock(return_value=[])
                with patch("permit.Permit.filter_objects", new_callable=AsyncMock):
                    pass
                monkeypatch.setattr(client, "check", AsyncMock(return_value=True))
                mocker.patch.object(client, "authorized_users", return_value=[])
            """
        },
    )
    expected = [("test_app.py", line, "A2", REVIEW) for line in (12, 13, 14, 16)]
    assert findings(tmp_path) == expected
    assert "use Mock or MagicMock" in scan.Project(tmp_path).scan()[0].message

    # Without the blocking client in the project, an AsyncMock of these methods is right.
    write(tmp_path, {"test_app.py": "from unittest.mock import AsyncMock\nclient.authorized_users = AsyncMock()\n"})
    assert findings(tmp_path) == []


def test_scanner_follows_module_aliases_to_removed_names(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            import permit as p
            import permit.api.context as ctx
            from permit import api as permit_api
            from permit.enforcement import interfaces

            VERSION = p.PYDANTIC_VERSION
            LEVEL = ctx.ApiKeyLevel.WAIT_FOR_INIT
            OTHER = permit_api.context.ApiKeyLevel
            TOKEN = interfaces.JWT
            KEEP = p.utils.pydantic_version.PYDANTIC_VERSION
            """
        },
    )

    assert findings(tmp_path) == [
        ("app.py", 6, "A6", SAFE),
        ("app.py", 7, "A3", SAFE),
        ("app.py", 8, "A3", SAFE),
        ("app.py", 9, "A3", SAFE),
    ]


def test_scanner_follows_star_imports_to_removed_names(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            from permit.api.context import *
            from permit.enforcement.interfaces import *

            LEVEL = ApiKeyLevel.WAIT_FOR_INIT
            TOKEN: JWT = "x"


            def own(JWT):
                return JWT
            """
        },
    )

    assert findings(tmp_path) == [("app.py", 4, "A3", SAFE), ("app.py", 5, "A3", SAFE)]


def test_context_store_transform_is_described_as_it_behaved(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            from permit.utils.context import ContextStore

            store = ContextStore()
            store.register_transform(add_region)
            context = store.transform({"user": "u"})
            """
        },
    )
    messages = [item.message for item in scan.Project(tmp_path).scan()]

    # 2.x's transform() applied the registered functions when called directly; no check ever did.
    assert "the SDK never applied a registered transform" in messages[0]
    assert "It applied the functions registered with register_transform()" in messages[1]


def test_untraced_receivers_are_never_safe(tmp_path: Path):
    write(
        tmp_path,
        {
            "service.py": """
            async def load(client, key):
                user = await client.api.get_user(key)
                return await client.authorized_users("read", "doc")
            """,
        },
    )
    assert findings(tmp_path) == [("service.py", 2, "D2", REVIEW)]

    # Once the project uses the blocking client somewhere, an untraced await is a question too.
    write(tmp_path, {"blocking.py": "from permit.sync import Permit\n"})
    assert findings(tmp_path) == [("service.py", 2, "D2", REVIEW), ("service.py", 3, "A2", REVIEW)]


def test_a_name_bound_in_a_function_hides_the_module_level_value(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            import asyncio

            from pydantic import BaseModel

            from permit.sync import Permit as SyncPermit

            permit = SyncPermit(token="t")
            client = SyncPermit(token="t")
            api = permit.api
            user = permit.api.users.get("u")


            class Mine(BaseModel):
                name: str


            def parameter(permit):
                return asyncio.run(permit.authorized_users("read", "doc"))


            def local():
                permit = make_client()
                return asyncio.run(permit.get_user_permissions("u"))


            def loop(clients):
                for client in clients:
                    asyncio.run(client.authorized_users("read", "doc"))


            def other_library(api):
                return api.get_user("octocat")


            def serialize(user: Mine):
                return user.model_dump()


            def own_model():
                user = Mine(name="x")
                return user.model_dump()


            def comprehension(users):
                return [user.model_dump() for user in users]


            def module_level():
                asyncio.run(client.authorized_users("read", "doc"))
                return user.model_dump(), api.get_role("admin")
            """
        },
    )

    # The parameter, local, loop and comprehension variables and the pydantic 2 model are not
    # the module-level client or SDK model of the same name, so nothing about them is SAFE.
    assert findings(tmp_path) == [
        ("app.py", 18, "A2", REVIEW),
        ("app.py", 23, "A2", REVIEW),
        ("app.py", 28, "A2", REVIEW),
        ("app.py", 32, "D2", REVIEW),
        ("app.py", 49, "A2", SAFE),
        ("app.py", 50, "D2", SAFE),
        ("app.py", 50, "T2", SAFE),
    ]


def test_a_name_annotated_with_an_sdk_model_is_one(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            from typing import List, Optional, Union

            from permit.api.models import UserRead


            def dump(
                a: UserRead, b: Optional[UserRead], c: "UserRead | None", d: Union[UserRead, int], e: List[UserRead]
            ):
                loaded: UserRead = load()
                return (
                    a.model_dump(),
                    b.model_dump(mode="json"),
                    c.model_dump_json(),
                    d.model_dump(),
                    e.model_dump(),
                    loaded.model_copy(),
                )
            """
        },
    )

    # d may be an int and e is a list, so neither is known to be an SDK model.
    assert findings(tmp_path) == [
        ("app.py", 11, "T2", SAFE),
        ("app.py", 12, "T2", REVIEW),
        ("app.py", 13, "T2", SAFE),
        ("app.py", 16, "T2", SAFE),
    ]


def test_a_value_bound_to_something_else_as_well_is_not_traced(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            import asyncio

            from permit import Permit
            from permit.sync import Permit as SyncPermit

            both = SyncPermit(token="t")
            if ASYNC:
                both = Permit(token="t")

            other = SyncPermit(token="t")
            other = make_other()

            lazy = None


            def connect():
                global lazy
                lazy = SyncPermit(token="t")


            class Owner:
                def __init__(self):
                    self.permit = SyncPermit(token="t")

                def owned(self):
                    return asyncio.run(self.permit.authorized_users("read", "doc"))


            class Borrower:
                def __init__(self, permit):
                    self.permit = permit

                def borrowed(self):
                    return asyncio.run(self.permit.authorized_users("read", "doc"))


            class Annotated:
                permit: SyncPermit

                def declared(self):
                    return asyncio.run(self.permit.authorized_users("read", "doc"))


            def run():
                asyncio.run(both.authorized_users("read", "doc"))
                both.api.get_user("u")
                asyncio.run(other.authorized_users("read", "doc"))
                other.api.get_user("u")
                asyncio.run(lazy.authorized_users("read", "doc"))
            """
        },
    )

    assert findings(tmp_path) == [
        ("app.py", 26, "A2", SAFE),
        ("app.py", 34, "A2", REVIEW),
        ("app.py", 41, "A2", SAFE),
        # Bound to both clients: .api exists on either, but asyncio.run() is right only on the async one.
        ("app.py", 45, "A2", REVIEW),
        ("app.py", 46, "D2", SAFE),
        # Bound to a client and to something else: nothing is safe.
        ("app.py", 47, "A2", REVIEW),
        ("app.py", 48, "D2", REVIEW),
        # `lazy = None` is a placeholder, not another value.
        ("app.py", 49, "A2", SAFE),
    ]


def test_starred_arguments_make_a_deprecated_call_need_review(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            from permit import Permit

            permit = Permit(token="t")


            async def run(args, kwargs):
                await permit.api.create_role(*args)
                await permit.api.update_role("admin", **kwargs)
                await permit.api.assign_role(*args)
                await permit.api.assign_role("u", "r", tenant_key="t")
            """
        },
    )

    assert findings(tmp_path) == [
        ("app.py", 7, "D2", REVIEW),
        ("app.py", 8, "D2", REVIEW),
        ("app.py", 9, "D2", REVIEW),
        ("app.py", 10, "D2", SAFE),
    ]


# ---------------------------------------------------------------------------
# W1, A4, A5: values that may be None
# ---------------------------------------------------------------------------


def test_only_visibly_optional_values_are_reported_for_w1(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            from typing import Optional

            from permit import Permit, UserUpdate

            permit = Permit(token="t")


            async def update(key: str, name: str, email: Optional[str], data: dict, kwargs: dict, n=None):
                await permit.api.users.update(key, UserUpdate(first_name=name))
                await permit.api.users.update(key, UserUpdate(email=email))
                await permit.api.users.update(key, UserUpdate(email=data.get("email")))
                await permit.api.users.update(key, UserUpdate(email=name if name else None))
                await permit.api.users.update(key, UserUpdate(email=n))
                await permit.api.users.update(key, UserUpdate(**kwargs))
                await permit.api.users.update(key, {"email": email})
                await permit.api.users.update(key, {"email": name})
                if email is not None:
                    await permit.api.users.update(key, UserUpdate(email=email))
                await permit.api.users.update(key, UserUpdate(email=email)) if email else None
            """
        },
    )

    assert findings(tmp_path) == [("app.py", line, "W1", REVIEW) for line in (10, 11, 12, 13, 15)]


def test_guarded_optional_fields_are_not_reported(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            from permit import Permit

            permit = Permit(token="t")


            async def ids():
                tuples = await permit.api.relationship_tuples.list()
                unguarded = [t.object_id.hex for t in tuples]
                in_comprehension = [t.object_id.hex for t in tuples if t.object_id is not None]
                in_and = [t.object_id and t.object_id.hex for t in tuples]
                for t in tuples:
                    if t.object_id is not None:
                        print(t.object_id.hex)
                return unguarded, in_comprehension, in_and
            """
        },
    )

    assert findings(tmp_path) == [("app.py", 8, "A5", REVIEW)]


def test_audit_log_objects_need_an_isinstance_check_not_a_none_check(tmp_path: Path):
    write(
        tmp_path,
        {
            "app.py": """
            from uuid import UUID

            from permit.api.models import AuditLogObjectsModel, DetailedAuditLogModel


            def users(raw):
                log = DetailedAuditLogModel.parse_obj(raw)
                unguarded = log.objects.user_object
                not_none = log.objects.user_object if log.objects is not None else None
                typed = log.objects.user_object if isinstance(log.objects, AuditLogObjectsModel) else None
                truthy = log.objects and log.objects.user_object
                config = log.pdp_config_id.hex if isinstance(log.pdp_config_id, UUID) else None
                return unguarded, not_none, typed, truthy, config
            """
        },
    )

    assert findings(tmp_path) == [("app.py", 8, "A4", REVIEW), ("app.py", 9, "A4", REVIEW)]


def test_audit_log_objects_default_to_an_empty_dict():
    """What A4 in both docs and the scanner's message say: `is not None` does not guard `objects`."""
    field = DetailedAuditLogModel.__fields__["objects"]

    assert field.required is False
    assert field.default == {}
    assert not isinstance(field.default, AuditLogObjectsModel)


# ---------------------------------------------------------------------------
# Dependency, CI and type-checker configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        pytest.param(
            "requirements/base.txt",
            """
            # comment
            -r other.txt
            permit==2.8.3  # pinned
            pydantic==2.3.0
            typing_extensions>=4.14.0
            permit @ git+https://github.com/permitio/permit-python
            """,
            [(3, "P1", SAFE), (4, "C3", SAFE), (6, "P1", REVIEW)],
            id="requirements",
        ),
        pytest.param(
            "requirements.txt",
            """
            # This file was autogenerated by uv via the following command:
            #    uv pip compile pyproject.toml -o requirements.txt
            aiohttp==3.12.14
                # via permit
            pydantic==1.10.13
                # via permit
            permit==2.8.3 \\
                --hash=sha256:0000000000000000000000000000000000000000000000000000000000000000
                # via sample-app (pyproject.toml)
            """,
            [(7, "P1", SAFE)],
            id="uv-compiled",
        ),
        pytest.param(
            "requirements/prod.txt",
            """
            loguru==0.7.2             # via permit
            permit==2.8.3             # via -r requirements/prod.in
            """,
            [(2, "P1", SAFE)],
            id="pip-compiled",
        ),
        pytest.param(
            "pyproject.toml",
            """
            [project]
            dependencies = [
                "pydantic[email]>=2.4.2",
                "permit[extra]>=2.0",
                "loguru~=0.7.0",
            ]
            keywords = ["permit"]

            [project.optional-dependencies]
            test = ["aiohttp>=3.12,<3.14"]

            [dependency-groups]
            dev = ["pydantic==1.10.13"]
            """,
            [(4, "P1", SAFE), (10, "C3", SAFE), (13, "C3", SAFE), (13, "D1", REVIEW)],
            id="pep621",
        ),
        pytest.param(
            "pyproject.toml",
            """
            [tool.poetry.dependencies]
            python = "^3.9"
            permit = "^2.8"
            pydantic = {version = "^1.10", extras = ["email"]}

            [tool.poetry.group.dev.dependencies]
            aiohttp = "3.12.14"
            """,
            [(2, "C1", REVIEW), (3, "P1", SAFE), (4, "D1", REVIEW), (7, "C3", SAFE)],
            id="poetry",
        ),
        pytest.param(
            "Pipfile",
            """
            [packages]
            permit = "*"
            loguru = "==0.7.0"

            [requires]
            python_version = "3.9"
            """,
            [(2, "P1", SAFE), (3, "C3", SAFE), (6, "C1", REVIEW)],
            id="pipfile",
        ),
        pytest.param(
            "setup.cfg",
            """
            [options]
            python_requires = >=3.8
            install_requires =
                permit>=2.0,<3
                aiohttp>=3.14.3

            [options.extras_require]
            old = pydantic<1.10
            """,
            [(2, "C1", REVIEW), (4, "P1", SAFE), (8, "C3", SAFE), (8, "D1", REVIEW)],
            id="setup.cfg",
        ),
        pytest.param(
            "setup.py",
            """
            from setuptools import setup

            setup(
                name="app",
                python_requires=">=3.9",
                install_requires=["permit==2.8.3", "httpx"],
                classifiers=["Programming Language :: Python :: 3.9"],
            )
            """,
            [(5, "C1", REVIEW), (6, "P1", SAFE), (7, "C1", REVIEW)],
            id="setup.py",
        ),
        pytest.param(
            "uv.lock",
            """
            [[package]]
            name = "permit"
            version = "2.8.3"
            source = { registry = "https://pypi.org/simple" }
            """,
            [(3, "P1", SAFE)],
            id="uv.lock",
        ),
        pytest.param(
            "Pipfile.lock",
            """
            {
                "default": {
                    "permit": {
                        "hashes": [],
                        "version": "==2.8.3"
                    }
                }
            }
            """,
            [(5, "P1", SAFE)],
            id="Pipfile.lock",
        ),
    ],
)
def test_dependency_files(tmp_path: Path, name: str, content: str, expected: List[Tuple[int, str, str]]):
    write(tmp_path, {name: content})

    assert findings(tmp_path) == [(name, line, change, safety) for line, change, safety in expected]


@pytest.mark.parametrize(
    ("name", "content", "lines"),
    [
        pytest.param(
            ".github/workflows/ci.yml",
            """
            jobs:
              test:
                strategy:
                  matrix:
                    python-version:
                      - "3.9"
                      - "3.12"
                steps:
                  - uses: actions/setup-python@v5
                    with:
                      python-version: "3.8"
            """,
            [6, 11],
            id="github-actions",
        ),
        pytest.param(
            ".circleci/config.yml", "jobs:\n  test:\n    docker:\n      - image: cimg/python:3.9\n", [4], id="circleci"
        ),
        pytest.param(
            "tox.ini", "[tox]\nenvlist = py38, py310\n[testenv:lint]\nbasepython = python3.12\n", [2], id="tox"
        ),
        pytest.param(
            "Dockerfile.prod", "ARG PYTHON_VERSION=3.9\nFROM python:${PYTHON_VERSION}\n", [1], id="dockerfile-arg"
        ),
        pytest.param("runtime.txt", "python-3.9.18\n", [1], id="runtime.txt"),
        pytest.param(".tool-versions", "nodejs 20.1.0\npython 3.9.18 3.12.1\n", [2], id="tool-versions"),
        pytest.param("mypy.ini", "[mypy]\npython_version = 3.9\n", [2], id="mypy"),
        pytest.param("pyrightconfig.json", '{\n  "pythonVersion": "3.8"\n}\n', [2], id="pyright"),
        pytest.param("pyproject.toml", '[project]\nrequires-python = "~=3.9"\n', [2], id="compatible-release"),
        pytest.param("pyproject.toml", '[project]\nrequires-python = ">3.9"\n', [2], id="greater-than"),
        pytest.param("pyproject.toml", '[project]\nrequires-python = ">=3.10"\n', [], id="310-floor"),
        pytest.param("pyproject.toml", '[project]\nrequires-python = "==3.12.*"\n', [], id="312-wildcard"),
        pytest.param(".python-version", "3.10\n", [], id="python-version-310"),
        pytest.param("Dockerfile", "FROM python:3.13-slim AS build\n", [], id="dockerfile-313"),
    ],
)
def test_python_pins_below_310(tmp_path: Path, name: str, content: str, lines: List[int]):
    write(tmp_path, {name: content})

    assert findings(tmp_path) == [(name, line, "C1", REVIEW) for line in lines]


def test_type_checker_settings_that_hide_permit(tmp_path: Path):
    write(
        tmp_path,
        {
            "mypy.ini": """
            [mypy]
            strict = True

            [mypy-permit.*,loguru]
            ignore_missing_imports = True

            [mypy-other.*]
            ignore_missing_imports = True
            """,
            "setup.cfg": """
            [mypy-permit]
            follow_imports = skip
            """,
            "app.py": """
            from permit import (  # type: ignore[import-untyped]
                Permit,
            )
            import httpx  # type: ignore
            import permit.sync  # pyright: ignore[reportMissingTypeStubs]
            from permit.config import PermitConfig  # type: ignore[import-untyped, attr-defined]
            """,
            "pyproject.toml": """
            [project]
            dependencies = ["httpx>=0.27"]

            [[tool.mypy.overrides]]
            module = [
                "loguru",
                "permit.*",
            ]
            ignore_missing_imports = true

            [[tool.mypy.overrides]]
            module = "permit"
            disallow_untyped_calls = false
            """,
        },
    )

    assert findings(tmp_path) == [
        ("app.py", 1, "T1", SAFE),
        ("app.py", 5, "T1", SAFE),
        ("app.py", 6, "T1", REVIEW),
        ("mypy.ini", 4, "T1", SAFE),
        ("pyproject.toml", 7, "T1", SAFE),
        ("setup.cfg", 1, "T1", SAFE),
    ]


def test_warnings_as_errors_matter_only_on_pydantic_1(tmp_path: Path):
    config = '[tool.pytest.ini_options]\nfilterwarnings = [\n    "error",\n]\n'
    write(tmp_path, {"pyproject.toml": config, "requirements.txt": "pydantic>=2.8\n"})
    assert findings(tmp_path) == []

    write(tmp_path, {"requirements.txt": "pydantic<2\n"})
    assert findings(tmp_path) == [
        ("pyproject.toml", 3, "D1", REVIEW),
        ("requirements.txt", 1, "D1", REVIEW),
    ]

    write(tmp_path, {"pytest.ini": "[pytest]\naddopts = -W error\n"})
    assert ("pytest.ini", 2, "D1", REVIEW) in findings(tmp_path)


def test_warning_filters_written_for_the_2x_text_need_review(tmp_path: Path):
    write(
        tmp_path,
        {
            "pyproject.toml": """
            [tool.pytest.ini_options]
            filterwarnings = [
                "ignore:use permit.api:DeprecationWarning",
                "ignore:permit\\\\.api\\\\.\\\\w+\\\\(\\\\) is deprecated:DeprecationWarning",
            ]
            """,
            "setup.cfg": "[tool:pytest]\nfilterwarnings =\n    ignore:use permit\\.elements:DeprecationWarning\n",
            "conftest.py": """
            import warnings

            import pytest

            warnings.filterwarnings("ignore", message=r"use permit\\.api", category=DeprecationWarning)
            pytest.mark.filterwarnings("ignore:use permit.api.users.get")
            EXPECTED = "permit.api.get_user() is deprecated ...; use permit.api.users.get() instead."
            """,
        },
    )

    # The 3.x filter and the 3.x message itself, where "use permit.api" is not at the start, are fine.
    assert findings(tmp_path) == [
        ("conftest.py", 5, "D2", REVIEW),
        ("conftest.py", 6, "D2", REVIEW),
        ("pyproject.toml", 3, "D2", REVIEW),
        ("setup.cfg", 3, "D2", REVIEW),
    ]


def test_httpx_counts_as_declared_when_any_dependency_file_declares_it(tmp_path: Path):
    write(tmp_path, {"app.py": "import httpx\nimport anyio\n", "requirements-dev.txt": "httpx==0.28.1\n"})

    assert findings(tmp_path) == [("app.py", 2, "C2", REVIEW)]


def test_every_package_that_left_the_tree_is_reported_when_imported_undeclared(tmp_path: Path):
    packages = ["httpx", "zipp", "httpcore", "h11", "anyio", "certifi", "sniffio", "exceptiongroup"]
    write(tmp_path, {"app.py": "".join(f"import {name}\n" for name in packages)})

    assert findings(tmp_path) == [("app.py", 1, "C2", SAFE)] + [
        ("app.py", line, "C2", REVIEW) for line in range(2, len(packages) + 1)
    ]
    assert set(scan.TRANSITIVE_PACKAGES) == set(packages)
    # Each is in the C2 section of both docs, so the docs and the scanner name the same set.
    for path in (MIGRATION, CHANGES):
        section = doc_section(path, "C2")
        assert {name for name in packages if f"`{name}`" in section} == set(packages), path.name


def test_a_compiled_requirements_file_is_a_lock_not_a_declaration(tmp_path: Path):
    write(
        tmp_path,
        {
            "pyproject.toml": '[project]\ndependencies = ["permit>=2.8,<3"]\n',
            "requirements.txt": """
            # This file was autogenerated by uv via the following command:
            #    uv pip compile pyproject.toml -o requirements.txt
            httpx==0.28.1
                # via permit
            permit==2.8.3
                # via sample-app (pyproject.toml)
            """,
            "app.py": "import httpx\n",
        },
    )
    project = scan.Project(tmp_path)

    # Regenerating the lock after the upgrade drops httpx, so the import needs its own declaration.
    assert [(item.path, item.line, item.change, item.safety) for item in project.scan()] == [
        ("app.py", 1, "C2", SAFE),
        ("pyproject.toml", 2, "P1", SAFE),
        ("requirements.txt", 5, "P1", SAFE),
    ]
    assert "don't edit this file" in project.scan()[2].message
    assert project.summary()["httpx_declared"] is False
    assert project.summary()["permit_locked"] == ["requirements.txt:5: 2.8.3"]


# ---------------------------------------------------------------------------
# What the scanner walks, and how it behaves as a command
# ---------------------------------------------------------------------------


def test_scanner_skips_environments_and_build_output(tmp_path: Path):
    deprecated_call = "from permit import Permit\nPermit(token='t').api.get_user('u')\n"
    write(
        tmp_path,
        {
            ".venv/lib/site.py": deprecated_call,
            "env/pyvenv.cfg": "home = /usr/bin\n",
            "env/lib/site.py": deprecated_call,
            "build/lib/app.py": deprecated_call,
            "node_modules/pkg/tool.py": deprecated_call,
            "lib/python3.9/site-packages/permit/api.py": deprecated_call,
            "src/app.egg-info/requires.txt": "permit==2.8.3\n",
            "src/app.py": deprecated_call,
        },
    )

    assert findings(tmp_path) == [("src/app.py", 2, "D2", SAFE)]


def test_a_file_that_does_not_parse_is_skipped_and_reported(tmp_path: Path):
    write(tmp_path, {"broken.py": "def (:\n", "app.py": "import permit\npermit.PYDANTIC_VERSION\n"})
    project = scan.Project(tmp_path)

    assert [(item.path, item.change) for item in project.scan()] == [("app.py", "A6")]
    assert [item["path"] for item in project.skipped] == ["broken.py"]


def test_scanner_does_not_modify_the_project():
    root = FIXTURES / "v2_app"

    def digest() -> Dict[str, str]:
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}

    before = digest()
    subprocess.run([sys.executable, str(SCANNER), str(root)], capture_output=True, check=True)
    assert digest() == before


@pytest.mark.parametrize(
    ("arguments", "status"),
    [
        pytest.param(["{fixture}"], 0, id="findings-exit-0"),
        pytest.param(["{fixture}", "--json"], 0, id="json-exit-0"),
        pytest.param(["{missing}"], 2, id="missing-directory"),
        pytest.param(["--unknown-flag"], 2, id="unknown-flag"),
    ],
)
def test_exit_status_is_non_zero_only_for_usage_errors(tmp_path: Path, arguments: List[str], status: int):
    values = {"fixture": str(FIXTURES / "v2_app"), "missing": str(tmp_path / "missing")}
    command = [sys.executable, str(SCANNER), *(argument.format(**values) for argument in arguments)]

    result = subprocess.run(command, capture_output=True, text=True, check=False)

    assert result.returncode == status, result.stderr


def test_scanner_uses_only_the_standard_library_and_python_38_syntax():
    source = SCANNER.read_text()
    tree = ast.parse(source, feature_version=(3, 8))
    imported = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    } | {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert imported <= sys.stdlib_module_names
    # Standard-library APIs newer than 3.8 that ast.parse's feature_version cannot see.
    for newer in (".removeprefix(", ".removesuffix(", "ast.unparse", "strict=", "tomllib", "zoneinfo"):
        assert newer not in source, newer
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            assert node.value.id not in ("list", "dict", "set", "tuple", "type"), "builtin generics need 3.9"


# ---------------------------------------------------------------------------
# The skill package
# ---------------------------------------------------------------------------


def frontmatter() -> Dict[str, str]:
    text = (SKILL_DIR / "SKILL.md").read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(": ")
        assert separator, f"not a single-line `key: value` entry: {line!r}"
        fields[key] = value
    return fields


def test_skill_frontmatter_has_only_a_valid_name_and_description():
    fields = frontmatter()

    assert set(fields) == {"name", "description"}
    assert fields["name"] == SKILL_DIR.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"])
    assert len(fields["name"]) <= 64
    description = fields["description"]
    assert 0 < len(description) <= 1024
    assert "<" not in description
    assert ">" not in description
    assert ": " not in description, "a colon and a space end an unquoted YAML value"
    for trigger in ("permit-python", "permitio", "2.x", "DeprecationWarning"):
        assert trigger in description


def test_skill_passes_the_skill_creator_validator():
    quick_validate = pytest.importorskip("quick_validate", reason="skill-creator's quick_validate is not on the path")

    valid, message = quick_validate.validate_skill(SKILL_DIR)

    assert valid, message


def flat(text: str) -> str:
    """Text with its line wrapping undone, so a phrase can be found wherever the lines break."""
    return " ".join(text.split())


def skill_step(number: int) -> str:
    text = (SKILL_DIR / "SKILL.md").read_text()
    match = re.search(rf"^## {number}\. .*?(?=^## )", text + "\n## end", re.MULTILINE | re.DOTALL)
    assert match, f"SKILL.md has no step {number}"
    return flat(match.group(0))


def test_skill_stops_on_any_python_below_310_before_editing_anything():
    preflight = skill_step(1)

    assert "Stop if anything says Python below 3.10:" in preflight
    assert "the interpreter the project runs under, or any C1 finding" in preflight
    assert "Edit nothing." in preflight
    assert "[Staying on 2.x](#staying-on-2x)" in preflight
    assert "Continue only when the user confirms" in preflight
    assert "Raise the C1 pins the user approved in step 1" in skill_step(3)


def test_skill_leaves_judgement_calls_and_checks_to_the_project():
    assert "Don't guess." in skill_step(5)
    assert "Remove imports an edit leaves unused" in skill_step(4)
    verify = skill_step(6)
    for check in ("tests", "type checker", "linter", "deprecation warnings as errors", "Re-run the scan"):
        assert check in verify, check


def test_skill_is_self_contained_and_small():
    files = sorted(
        path.relative_to(SKILL_DIR).as_posix()
        for path in SKILL_DIR.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    assert files == ["SKILL.md", "references/changes.md", "scripts/scan.py"]
    for path in (SKILL_DIR / "SKILL.md", CHANGES):
        text = path.read_text()
        assert "MIGRATION.md" not in text
        # A path out of the skill folder, not the ellipsis in `GET .../resources`.
        assert not re.search(r"(?<![.\w])\.\./", text)
    assert len((SKILL_DIR / "SKILL.md").read_text().splitlines()) < 500
    for link in re.findall(r"`(references/[\w./-]+|scripts/[\w./-]+)`", (SKILL_DIR / "SKILL.md").read_text()):
        assert (SKILL_DIR / link).is_file(), link


# ---------------------------------------------------------------------------
# The docs against each other, the scanner and the SDK
# ---------------------------------------------------------------------------


def doc_section(path: Path, change: str) -> str:
    """The text under a change's `### ID. Title` heading, up to the next heading."""
    match = re.search(rf"^### {change}\. .*?(?=^##)", path.read_text() + "\n## end", re.MULTILINE | re.DOTALL)
    assert match, f"{path.name} has no section for {change}"
    return match.group(0)


def change_headings(path: Path) -> Dict[str, str]:
    headings = re.findall(r"^#{2,4} ([A-Z]\d+)\. (.+)$", path.read_text(), re.MULTILINE)
    ids = [change for change, _ in headings]
    assert len(ids) == len(set(ids)), f"{path.name} has a change ID twice"
    return dict(headings)


def test_every_change_id_is_in_both_docs_under_the_same_heading():
    catalogue = change_headings(CHANGES)

    assert catalogue == change_headings(MIGRATION)
    for change, title in scan.TITLES.items():
        assert catalogue.get(change) == title, change


def test_the_catalogue_contents_list_every_change():
    text = CHANGES.read_text()
    contents = text.split("## Contents", 1)[1].split("\n### ", 1)[0]

    for change in change_headings(CHANGES):
        assert f"[{change}" in contents, change


def deprecated_mapping() -> Dict[str, str]:
    source = (REPO_ROOT / "permit" / "api" / "deprecated.py").read_text()
    mapping = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_removal_notice":
            old, new = (ast.literal_eval(arg) for arg in node.args)
            mapping[old] = new
    return mapping


def doc_mapping(path: Path) -> Dict[str, Tuple[str, Optional[Dict[str, str]]]]:
    rows = re.findall(
        r"^\| `permit\.api\.(\w+)\(\)` \| `(permit\.[\w.]+)\(\)` \|(.*)\|$", path.read_text(), re.MULTILINE
    )
    mapping: Dict[str, Tuple[str, Optional[Dict[str, str]]]] = {}
    for old, new, keywords in rows:
        assert old not in mapping, f"{path.name} lists {old} twice"
        renames = dict(re.findall(r"`(\w+)=` (?:to|becomes) `(\w+)=`", keywords))
        mapping[old] = (new, None if "three arguments" in keywords else renames)
    return mapping


def test_the_21_method_mapping_matches_the_sdk_in_both_docs_and_the_scanner():
    sdk = deprecated_mapping()
    scanner = {old: (f"permit.{new}", renames) for old, (new, renames) in scan.DEPRECATED_METHODS.items()}

    assert len(sdk) == 21
    assert {old: new for old, (new, _) in scanner.items()} == sdk
    assert doc_mapping(CHANGES) == scanner
    assert doc_mapping(MIGRATION) == scanner


def test_the_keyword_renames_match_the_sdk_signatures():
    """A rename is where the deprecated method and its replacement name the same position differently."""
    client = Permit(PermitConfig(token="permit_key_test"))
    for old, (new, renames) in scan.DEPRECATED_METHODS.items():
        replacement = client
        for part in new.split("."):
            replacement = getattr(replacement, part)
        old_parameters = list(inspect.signature(getattr(client.api, old)).parameters)
        new_parameters = list(inspect.signature(replacement).parameters)
        if renames is None:
            assert old_parameters == ["user_key", "role_key", "tenant_key"], old
            continue
        expected = {
            name: new_parameters[index]
            for index, name in enumerate(old_parameters)
            if index < len(new_parameters) and name != new_parameters[index]
        }
        assert renames == expected, old
        assert len(old_parameters) == len(new_parameters), old


def test_the_removed_names_really_are_gone():
    for module_name, name in scan.REMOVED:
        module = importlib.import_module(module_name)
        assert not hasattr(module, name), f"{module_name}.{name} still exists"
