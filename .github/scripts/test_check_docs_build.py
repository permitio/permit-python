"""Contract tests for check_docs_build.py, the docs build gate.

These pin what test.yml's docs job and docs-deploy.yml rely on: the gate fails
on a failed build and on every kind of warning line, Griffe's included, even when
the build exits 0; it exits 2, never 0 or 1, when the build did not run to the
end; and it streams the build's log as it arrives. No Zensical: each test runs a
fake build command that prints a planted log in the format Zensical 0.0.65
prints, and writes the site or not; the default build's tests put a fake zensical
package on PYTHONPATH. The last tests read both workflows with yq (mikefarah v4)
and check that they build the site the same way, with the same uv and Python,
through the gate.

Run with:
uv run --only-dev pytest -c .github/scripts/pytest.ini .github/scripts/test_check_docs_build.py
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "check_docs_build.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

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
# What Zensical 0.0.65 prints when the Griffe extension raises: its own traceback, which ends
# with the extension's exception, then the extension's, which ends at a blank line.
PLUGIN_ERROR = "RuntimeError: Python error: ValueError: Cannot read the deprecation message 'M'"
PLUGIN_CRASH = (
    "Traceback (most recent call last):\n"
    '  File "/venv/bin/zensical", line 10, in <module>\n'
    "    sys.exit(cli())\n"
    "             ^^^^^\n"
    '  File "/venv/lib/zensical/main.py", line 81, in execute_build\n'
    "    build(os.path.abspath(config_file), kwargs)\n"
    f"{PLUGIN_ERROR}\n"
    "Traceback (most recent call last):\n"
    '  File "/venv/lib/zensical/markdown/render.py", line 103, in render\n'
    "    content = md.convert(content)\n"
    "              ^^^^^^^^^^^^^^^^^^^\n"
    '  File "/repo/scripts/docs_griffe_extension.py", line 78, in _evaluate_message\n'
    "    raise ValueError(msg)\n"
    "\n"
)


def fake_build(
    tmp_path: Path,
    log: str = CLEAN_LOG,
    *,
    exit_code: int = 0,
    site: str | None = "site",
    out: str = "",
    pages: dict[str, str] | None = None,
) -> list[str]:
    """Return a build command that prints a planted log and exits with `exit_code`.

    It prints `out` to stdout and `log` to stderr, as Zensical splits its output,
    and writes `pages` (path in the site -> content; by default an index.html with
    no links) under `site`, unless `site` is None.
    """
    script = tmp_path / "fake_build.py"
    writes_site = (
        "".join(
            f"Path({site!r}, {name!r}).parent.mkdir(parents=True, exist_ok=True)\n"
            f"Path({site!r}, {name!r}).write_text({content!r}, encoding='utf-8')\n"
            for name, content in (pages or {"index.html": "<html></html>"}).items()
        )
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
    assert "Aborted because --strict" not in report
    assert "Python error" not in report


def test_the_error_that_stopped_the_build_is_listed_first(tmp_path: Path) -> None:
    log = (
        "Build started\n"
        + zensical_diagnostic("page does not exist", "reference/index.md:7:18")
        + "1 issue found\n"
        + PLUGIN_CRASH
    )
    completed = run_gate(tmp_path, fake_build(tmp_path, log, exit_code=1, site=None))
    assert completed.returncode == 1
    report = verdict(completed)
    assert f"  The build raised 1 Python error(s):\n    {PLUGIN_ERROR}\n" in report
    assert report.index(PLUGIN_ERROR) < report.index("reference/index.md:7:18: Warning")


def test_a_traceback_fails_a_build_that_exited_0(tmp_path: Path) -> None:
    log = (
        "Build started\n"
        "Traceback (most recent call last):\n"
        '  File "/venv/lib/plugin.py", line 1, in render\n'
        "KeyError: 'page'\n"
        "\n"
        "During handling of the above exception, another exception occurred:\n"
        "\n"
        "Traceback (most recent call last):\n"
        '  File "/venv/lib/plugin.py", line 3, in render\n'
        "OSError: [Errno 2] No such file or directory: 'page.md'\n"
        "Build finished in 0.3s\n"
    )
    completed = run_gate(tmp_path, fake_build(tmp_path, log))
    assert completed.returncode == 1
    report = verdict(completed)
    assert "The build raised 2 Python error(s):" in report
    assert "    KeyError: 'page'\n" in report
    assert "    OSError: [Errno 2] No such file or directory: 'page.md'\n" in report
    assert "During handling" not in report
    assert "Build finished" not in report
    assert "exited with status" not in report


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


# --- exit 1: a broken link in the site ------------------------------------------

# A site in which every relative link reaches its page or file and its id.
LINKED_SITE = {
    "index.html": (
        '<html><head><link rel="stylesheet" href="assets/site.css">'
        '<link rel="canonical" href="https://permitio.github.io/permit-python/"></head>'
        '<body id="top"><a href="guide/">Guide</a> <a href="guide/#setup">Setup</a>'
        ' <a href="guide/index.html#setup">Setup</a> <a href="guide/#caf%C3%A9">Café</a>'
        ' <a href="#top">Top</a> <a href="#">Top</a> <a href="./">Home</a>'
        ' <a href="?q=check">Search</a> <a href="https://docs.permit.io/#elsewhere">Guides</a>'
        ' <a href="/permit-python/absolute/">Absolute</a> <a href="mailto:a@example.com">Mail</a>'
        ' <img src="assets/logo.png" alt=""></body></html>'
    ),
    "guide/index.html": (
        '<html><body><h2 id="setup">Setup</h2><h2 id="café">Café</h2><a name="legacy"></a>'
        ' <a href="..">Home</a> <a href="../#top">Top</a> <a href="#legacy">Legacy</a>'
        ' <script src="../assets/site.js"></script></body></html>'
    ),
    "assets/site.css": "",
    "assets/site.js": "",
    "assets/logo.png": "",
    # Not checked: the theme's skip link has no target here, and relative links would
    # resolve against whatever URL the page is returned for.
    "404.html": '<html><body><a href="#__skip">Skip</a> <a href="nope/">Nope</a></body></html>',
}


def test_a_site_whose_links_all_reach_their_target_passes(tmp_path: Path) -> None:
    completed = run_gate(tmp_path, fake_build(tmp_path, pages=LINKED_SITE))
    assert completed.returncode == 0, completed.stdout
    assert "every relative link in it reaches its page and anchor" in verdict(completed)


@pytest.mark.parametrize(
    ("element", "problem"),
    [
        ('<a href="nope/">x</a>', "nope/: nope/index.html does not exist"),
        ('<a href="CONTRIBUTING.md">x</a>', "CONTRIBUTING.md: CONTRIBUTING.md does not exist"),
        ('<a href="guide/#nope">x</a>', "guide/#nope: guide/index.html has no id 'nope'"),
        ('<a href="#nope">x</a>', "#nope: index.html has no id 'nope'"),
        ('<a href="../outside/">x</a>', "../outside/: it points outside the site"),
        ('<img src="assets/gone.png" alt="">', "assets/gone.png: assets/gone.png does not exist"),
    ],
    ids=["page", "file", "anchor on another page", "anchor on the page", "outside", "source"],
)
def test_a_broken_link_fails_a_build_that_passed(
    tmp_path: Path, element: str, problem: str
) -> None:
    pages = {**LINKED_SITE, "index.html": f'<html><body id="top">{element}</body></html>'}
    completed = run_gate(tmp_path, fake_build(tmp_path, pages=pages))
    assert completed.returncode == 1
    report = verdict(completed)
    assert f"  The site has 1 broken link(s):\n    index.html: {problem}\n" in report


def test_a_broken_link_is_listed_once_per_page(tmp_path: Path) -> None:
    broken = '<a href="#nope">x</a>'
    pages = {
        **LINKED_SITE,
        "index.html": f"<html><body>{broken}{broken}</body></html>",
        "guide/index.html": f'<html><body><a href="../#nope">x</a>{broken}</body></html>',
    }
    completed = run_gate(tmp_path, fake_build(tmp_path, pages=pages))
    assert completed.returncode == 1
    report = verdict(completed)
    assert "  The site has 3 broken link(s):\n" in report
    assert report.count("    index.html: #nope: index.html has no id 'nope'\n") == 1
    assert "    guide/index.html: ../#nope: index.html has no id 'nope'\n" in report
    assert "    guide/index.html: #nope: guide/index.html has no id 'nope'\n" in report


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


def test_exit_2_when_zensical_is_not_installed(tmp_path: Path) -> None:
    # -S leaves out site-packages, where the docs group installs zensical. The gate is stdlib
    # only, so it runs without them.
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    completed = subprocess.run(  # noqa: S603 - runs the script under test with this interpreter
        [sys.executable, "-S", str(SCRIPT)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 2
    report = verdict(completed)
    assert "the build did not run: zensical is not installed for" in report
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


# --- the default build ------------------------------------------------------------


def fake_zensical(tmp_path: Path, logged: str) -> Path:
    """A zensical package whose command line logs `logged` and writes the site.

    `logged` is the body of a function of a logger, run as the build renders the pages. The
    package goes on PYTHONPATH, ahead of a real zensical in site-packages.
    """
    package = tmp_path / "fake_packages" / "zensical"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "main.py").write_text(
        "import logging\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "def cli(prog_name):\n"
        "    assert prog_name == 'zensical', prog_name\n"
        "    assert sys.argv[1:] == ['build', '--strict', '--clean'], sys.argv\n"
        "    print('Build started', flush=True)\n"
        "    logger = logging.getLogger('some_extension')\n"
        f"    {logged}\n"
        "    Path('site').mkdir()\n"
        "    Path('site', 'index.html').write_text('<html></html>', encoding='utf-8')\n",
        encoding="utf-8",
    )
    return package.parent


def run_default_build(tmp_path: Path, logged: str) -> subprocess.CompletedProcess[str]:
    packages = fake_zensical(tmp_path, logged)
    return subprocess.run(  # noqa: S603 - runs the script under test with this interpreter
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(packages)},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_the_default_build_runs_zensical_build_strict_clean(tmp_path: Path) -> None:
    completed = run_default_build(tmp_path, "logger.info('rendered a page')")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "rendered a page" not in completed.stdout


@pytest.mark.parametrize("level", ["warning", "error"])
def test_the_default_build_fails_on_a_record_of_any_logger(tmp_path: Path, level: str) -> None:
    # Without a handler, Python would print the bare message, which no pattern can match.
    completed = run_default_build(tmp_path, f"logger.{level}('planted record')")
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert f"    {level.upper()}:some_extension:planted record\n" in verdict(completed)


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


# --- the workflows ---------------------------------------------------------------


def workflow_step(workflow: str, job: str, name: str) -> dict[str, object]:
    yq = shutil.which("yq")
    if yq is None:
        pytest.fail("yq is not on PATH; this test reads the workflows with it")
    completed = subprocess.run(  # noqa: S603 - yq reads a workflow of this repository
        [yq, "-o=json", ".", str(REPO_ROOT / ".github" / "workflows" / workflow)],
        capture_output=True,
        text=True,
        check=True,
    )
    steps = json.loads(completed.stdout)["jobs"][job]["steps"]
    found = [step for step in steps if step.get("name") == name]
    assert len(found) == 1, f"expected one {name!r} step in job {job!r} of {workflow}"
    step: dict[str, object] = found[0]
    return step


@pytest.mark.parametrize("name", ["Install the docs dependencies", "Build the site"])
def test_ci_and_the_deploy_build_the_site_the_same_way(name: str) -> None:
    ci = workflow_step("test.yml", "docs", name)
    deploy = workflow_step("docs-deploy.yml", "build", name)
    assert ci == deploy


def test_ci_and_the_deploy_build_the_site_with_the_same_uv_and_python() -> None:
    ci = workflow_step("test.yml", "docs", "Install uv")
    deploy = workflow_step("docs-deploy.yml", "build", "Install uv")
    assert ci["uses"] == deploy["uses"]
    ci_inputs = ci["with"]
    deploy_inputs = deploy["with"]
    assert isinstance(ci_inputs, dict)
    assert isinstance(deploy_inputs, dict)
    for name in ("version-file", "python-version"):
        assert ci_inputs[name] == deploy_inputs[name], name
    # The deploy publishes what it builds, so it restores no cache.
    assert deploy_inputs["enable-cache"] is False


def test_the_workflows_build_the_site_through_the_gate() -> None:
    step = workflow_step("test.yml", "docs", "Build the site")
    assert "uv run --no-sync python .github/scripts/check_docs_build.py\n" in str(step["run"])
