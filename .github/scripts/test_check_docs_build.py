"""Contract tests for check_docs_build.py, the docs build gate.

These pin what test.yml's docs job and docs-deploy.yml rely on: the gate fails
on a failed build and on every kind of warning line, Griffe's included, even when
the build exits 0; it exits 2, never 0 or 1, when the build did not run to the
end; and it streams the build's log as it arrives. No Zensical: each test runs a
fake build command that prints a planted log in the format Zensical 0.0.65
prints, and writes the site or not.

Run with:
uv run --only-dev pytest -c .github/scripts/pytest.ini .github/scripts/test_check_docs_build.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "check_docs_build.py"

sys.path.insert(0, str(Path(__file__).parent))

import check_docs_build  # noqa: E402 - importable only once sys.path has its directory

GREY = "\x1b[38;5;246m"
RESET = "\x1b[0m"


def zensical_diagnostic(message: str, where: str) -> str:
    """A diagnostic as Zensical 0.0.65 prints it: a coloured label, then a box at `where`."""
    return (
        f"\x1b[33mWarning:{RESET} {message}\n"
        f"   {GREY}╭{RESET}{GREY}─{RESET}{GREY}[{RESET} {where} {GREY}]{RESET}\n"
        f"   {GREY}│{RESET}\n"
        f" {GREY}3 │{RESET} \x1b[38;5;249m[a](missing.md#nope){RESET}\n"
        f" \x1b[38;5;240m  │{RESET}     \x1b[33m─────┬────{RESET}  \n"
        f" \x1b[38;5;240m  │{RESET}          \x1b[33m╰──────{RESET} {message}\n"
        f"{GREY}───╯{RESET}\n"
    )


CLEAN_LOG = "Build started\nNo issues found\nBuild finished in 0.28s\n"
GRIFFE_WARNINGS = [
    "griffe: permit/api/users.py:20: No type or annotation for parameter 'y'",
    "griffe: permit/api/users.py:20: Parameter 'y' does not appear in the function signature",
]
# What Zensical prints when --strict stops a build on its diagnostics.
STRICT_ABORT = (
    "2 issues found\n"
    "Traceback (most recent call last):\n"
    '  File "/venv/bin/zensical", line 12, in <module>\n'
    "    sys.exit(cli())\n"
    "RuntimeError: Aborted because --strict flag is set\n"
)


def fake_build(
    tmp_path: Path,
    log: str = CLEAN_LOG,
    *,
    exit_code: int = 0,
    site: str | None = "site",
    out: str = "",
) -> list[str]:
    """Return a build command that prints a planted log and exits with `exit_code`.

    It prints `out` to stdout and `log` to stderr, as Zensical splits its output,
    and writes `site`/index.html unless `site` is None.
    """
    script = tmp_path / "fake_build.py"
    writes_site = (
        f"Path({site!r}).mkdir(parents=True, exist_ok=True)\n"
        f"Path({site!r}, 'index.html').write_text('<html></html>', encoding='utf-8')\n"
        if site is not None
        else ""
    )
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.stdout.write({out!r})\n"
        "sys.stdout.flush()\n"
        f"sys.stderr.write({log!r})\n"
        f"{writes_site}"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def run_gate(tmp_path: Path, command: list[str], *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - runs the script under test with this interpreter
        [sys.executable, str(SCRIPT), *options, "--", *command],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def verdict(completed: subprocess.CompletedProcess[str]) -> str:
    """The gate's own output: everything from its first line on."""
    return completed.stdout[completed.stdout.index(check_docs_build.PREFIX) :]


# --- passing ------------------------------------------------------------------


def test_a_clean_build_passes_and_its_log_comes_first(tmp_path: Path) -> None:
    completed = run_gate(tmp_path, fake_build(tmp_path, out="on stdout\n"))
    assert completed.returncode == 0, completed.stdout
    assert completed.stdout.index("on stdout") < completed.stdout.index("Build finished")
    assert completed.stdout.index("Build finished") < completed.stdout.index("passed")
    assert "The build wrote site and logged no warning" in completed.stdout


def test_lines_that_only_mention_warnings_pass(tmp_path: Path) -> None:
    log = (
        "Build started\n"
        "Copying the WARNINGS page and the griffe: examples\n"
        "warnings: none\n"
        "Rendered 'Warning: deprecated' admonitions\n"
        "No issues found\n"
    )
    completed = run_gate(tmp_path, fake_build(tmp_path, log))
    assert completed.returncode == 0, completed.stdout


def test_the_site_dir_option_names_where_the_site_is(tmp_path: Path) -> None:
    command = fake_build(tmp_path, site="build/html")
    completed = run_gate(tmp_path, command, "--site-dir", "build/html")
    assert completed.returncode == 0, completed.stdout


def test_the_command_needs_no_double_dash(tmp_path: Path) -> None:
    completed = subprocess.run(  # noqa: S603 - runs the script under test with this interpreter
        [sys.executable, str(SCRIPT), *fake_build(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout


# --- exit 1: a failed build or a warning --------------------------------------


def test_griffe_warnings_fail_a_build_that_exited_0(tmp_path: Path) -> None:
    log = "Build started\n" + "".join(f"{line}\n" for line in GRIFFE_WARNINGS) + "No issues found\n"
    completed = run_gate(tmp_path, fake_build(tmp_path, log))
    assert completed.returncode == 1
    report = verdict(completed)
    assert "The build log has 2 warning or error line(s):" in report
    for line in GRIFFE_WARNINGS:
        assert f"    {line}\n" in report
    assert "exited with status" not in report


@pytest.mark.parametrize(
    "message", ["page does not exist", "anchor does not exist", "unresolved autoref"]
)
def test_a_zensical_diagnostic_fails_and_names_its_place(tmp_path: Path, message: str) -> None:
    log = "Build started\n" + zensical_diagnostic(message, "index.md:3:5") + "1 issue found\n"
    completed = run_gate(tmp_path, fake_build(tmp_path, log))
    assert completed.returncode == 1
    assert f"    index.md:3:5: Warning: {message}\n" in verdict(completed)


def test_a_strict_abort_lists_its_diagnostics_and_the_exit_status(tmp_path: Path) -> None:
    log = (
        "Build started\n"
        + zensical_diagnostic("anchor does not exist", "api.md:3:14")
        + zensical_diagnostic("page does not exist", "index.md:3:5")
        + STRICT_ABORT
    )
    completed = run_gate(tmp_path, fake_build(tmp_path, log, exit_code=1))
    assert completed.returncode == 1
    report = verdict(completed)
    assert "The build exited with status 1." in report
    assert "    api.md:3:14: Warning: anchor does not exist\n" in report
    assert "    index.md:3:5: Warning: page does not exist\n" in report


@pytest.mark.parametrize(
    "line",
    [
        "mkdocstrings: permit.missing could not be found",
        "mkdocstrings_handlers: Could not render the signature of permit.Permit.check",
        "WARNING -  griffe: permit/api/users.py:20: Parameter 'y' does not appear",
        "WARNING:griffe:permit/api/users.py:20: Parameter 'y' does not appear",
        "ERROR    -  Config value 'nav': a page does not exist",
        "/venv/lib/markdown/core.py:120: DeprecationWarning: 'md_globals' is deprecated",
        "Error: page output escaped the site directory",
    ],
    ids=[
        "mkdocstrings",
        "mkdocstrings handler",
        "MkDocs format",
        "logging format",
        "error with its level",
        "Python warning",
        "Zensical error",
    ],
)
def test_every_kind_of_warning_line_fails(tmp_path: Path, line: str) -> None:
    completed = run_gate(tmp_path, fake_build(tmp_path, f"Build started\n{line}\nDone\n"))
    assert completed.returncode == 1
    assert f"    {line}\n" in verdict(completed)


def test_a_failed_build_with_no_warning_fails_with_its_status(tmp_path: Path) -> None:
    completed = run_gate(tmp_path, fake_build(tmp_path, "Build started\n", exit_code=3))
    assert completed.returncode == 1
    report = verdict(completed)
    assert "The build exited with status 3." in report
    assert "line(s)" not in report


def test_a_failed_build_fails_even_without_a_site(tmp_path: Path) -> None:
    completed = run_gate(tmp_path, fake_build(tmp_path, exit_code=1, site=None))
    assert completed.returncode == 1


def test_output_that_is_not_utf8_is_still_read(tmp_path: Path) -> None:
    script = tmp_path / "fake_build.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.stderr.buffer.write(b'\\xff\\xfe garbage\\n' + b'griffe: permit/x.py:1: Bad\\n')\n"
        "Path('site').mkdir()\n"
        "Path('site', 'index.html').write_text('<html></html>', encoding='utf-8')\n",
        encoding="utf-8",
    )
    completed = run_gate(tmp_path, [sys.executable, str(script)])
    assert completed.returncode == 1
    assert "    griffe: permit/x.py:1: Bad\n" in verdict(completed)


# --- exit 2: the build did not run to the end -----------------------------------


def test_exit_2_when_the_build_writes_no_site(tmp_path: Path) -> None:
    completed = run_gate(tmp_path, fake_build(tmp_path, site=None))
    assert completed.returncode == 2
    assert "did not write site/index.html" in verdict(completed)


def plant_index_html(tmp_path: Path) -> None:
    """Leave an index.html from an earlier build, last written an hour ago."""
    stale = tmp_path / "site" / "index.html"
    stale.parent.mkdir()
    stale.write_text("<html></html>", encoding="utf-8")
    an_hour_ago = time.time() - 3600
    os.utime(stale, (an_hour_ago, an_hour_ago))


def test_exit_2_when_index_html_is_left_from_an_earlier_build(tmp_path: Path) -> None:
    plant_index_html(tmp_path)
    completed = run_gate(tmp_path, fake_build(tmp_path, site=None))
    assert completed.returncode == 2
    assert "did not write site/index.html" in verdict(completed)


def test_a_build_that_writes_over_an_earlier_index_html_passes(tmp_path: Path) -> None:
    plant_index_html(tmp_path)
    completed = run_gate(tmp_path, fake_build(tmp_path))
    assert completed.returncode == 0, completed.stdout


def test_exit_2_when_the_site_is_elsewhere(tmp_path: Path) -> None:
    completed = run_gate(tmp_path, fake_build(tmp_path), "--site-dir", "public")
    assert completed.returncode == 2
    assert "Check that site_dir in mkdocs.yml is public." in verdict(completed)


def test_exit_2_when_the_command_cannot_start(tmp_path: Path) -> None:
    completed = run_gate(tmp_path, [str(tmp_path / "no-such-zensical"), "build"])
    assert completed.returncode == 2
    assert "the build did not run: could not start" in verdict(completed)


def test_exit_2_when_the_default_command_cannot_start(tmp_path: Path) -> None:
    completed = subprocess.run(  # noqa: S603 - runs the script under test with this interpreter
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env={"PATH": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 2
    report = verdict(completed)
    assert "could not start 'zensical'" in report
    assert "Run the gate in the docs environment: uv run --locked --group docs python" in report


def test_exit_2_when_a_signal_stops_the_build(tmp_path: Path) -> None:
    script = tmp_path / "fake_build.py"
    script.write_text(
        "import os\nimport signal\nprint('Build started', flush=True)\n"
        "os.kill(os.getpid(), signal.SIGKILL)\n",
        encoding="utf-8",
    )
    completed = run_gate(tmp_path, [sys.executable, str(script)])
    assert completed.returncode == 2
    assert f"signal {int(signal.SIGKILL)} stopped it" in verdict(completed)


def test_exit_2_when_the_gate_itself_breaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(log: list[str]) -> list[str]:
        raise ValueError(len(log))

    monkeypatch.setattr(check_docs_build, "find_warnings", broken)
    monkeypatch.chdir(tmp_path)
    assert check_docs_build.main(["--", *fake_build(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "the gate itself failed" in captured.out
    assert "ValueError" in captured.err


# --- streaming ------------------------------------------------------------------


def test_the_log_is_streamed_as_it_arrives(tmp_path: Path) -> None:
    """The fake build prints a line, then waits for the test to see it before it ends."""
    seen = tmp_path / "seen"
    script = tmp_path / "fake_build.py"
    script.write_text(
        "import sys, time\n"
        "from pathlib import Path\n"
        "print('first line', flush=True)\n"
        "deadline = time.monotonic() + 20\n"
        f"while not Path({str(seen)!r}).exists():\n"
        "    if time.monotonic() > deadline:\n"
        "        sys.exit('nobody saw the first line')\n"
        "    time.sleep(0.05)\n"
        "Path('site').mkdir()\n"
        "Path('site', 'index.html').write_text('<html></html>', encoding='utf-8')\n",
        encoding="utf-8",
    )
    with subprocess.Popen(  # noqa: S603 - runs the script under test with this interpreter
        [sys.executable, str(SCRIPT), "--", sys.executable, str(script)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        text=True,
    ) as gate:
        assert gate.stdout is not None
        assert gate.stdout.readline() == "first line\n"
        seen.touch()
        rest = gate.stdout.read()
    assert gate.returncode == 0, rest
