#!/usr/bin/env python3
"""Build the API reference site and fail on any warning in the build log.

Runs the site build, streams its log, and reads every line of it. Zensical's
--strict fails the build on Zensical's own diagnostics: a link to a page or an
anchor that does not exist, an unresolved cross-reference or link reference. It
does not count what Griffe, mkdocstrings, Markdown extensions or the Griffe
extension log while the build renders the pages, and the build still exits 0.
Zensical sets up no logging handler, so Python would print such a record as its
bare message. The default build therefore runs Zensical's command line under a
root handler that prints each record of level WARNING and up with its level and
logger (`WARNING:<logger>:<message>`), and this script fails on those lines.

Run it in the docs environment, where zensical is installed:

    uv run --locked --group docs python .github/scripts/check_docs_build.py

An error from uv itself, such as an out-of-date uv.lock (exit 1) or a group
that does not exist (exit 2), comes before the gate starts, and no verdict
follows it. CI installs the docs group in a step of its own (uv sync --locked
--group docs), so there such an error fails that step, not the build step.

The default build is `zensical build --strict --clean`, run with this script's
interpreter. --clean matters: Zensical caches rendered pages in .cache/ and does
not render an unchanged page again, so without it a second build would not
repeat the Griffe warnings of the first. Zensical has no option for the output
directory; it writes to site_dir in mkdocs.yml, which --site-dir must name. A
command given after -- runs as given, without the logging handler.

Contract (test.yml's docs job and docs-deploy.yml depend on it):

* Exit 0: the build exited 0, its log holds no warning, and it wrote
  <site-dir>/index.html.
* Exit 1: the build exited non-zero, or its log holds a warning: a Zensical
  diagnostic (`Warning: ...` or `Error: ...`), a record printed with its level
  (`WARNING:...`, as the default build prints them, or `WARNING -  ...`, as
  MkDocs does), a Griffe or mkdocstrings record printed without one (`griffe: ...`,
  `mkdocstrings: ...`), a Python warning (`path:line: SomeWarning: ...`), or a
  Python traceback.
* Exit 2: the build did not run to the end, so there is no result: zensical is
  not installed for this interpreter (default build only), the command could
  not be started, a signal stopped it, or it exited 0 without writing
  <site-dir>/index.html (one that is still the file it was before the build does
  not count). Any error in this script is also exit 2, never a pass.
* The build's stdout and stderr are streamed to stdout as they arrive. The
  verdict follows on stdout. It lists the exception each traceback ends with
  first, since a crash also leaves knock-on warnings, such as a page that links
  to the page that failed. Then one line per warning, a Zensical diagnostic
  prefixed with the place it points at.

Stdlib only.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shlex
import subprocess
import sys
import traceback
from pathlib import Path

ZENSICAL_ARGUMENTS = ("build", "--strict", "--clean")
# Zensical's command line, as its `zensical` script runs it, under a root logging handler that
# prints each record with its level and logger, so that LOGGED_WARNINGS can find every one.
ZENSICAL_UNDER_A_LOGGING_HANDLER = (
    "import logging, sys\n"
    "logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')\n"
    "from zensical.main import cli\n"
    "sys.exit(cli(prog_name='zensical'))\n"
)
DEFAULT_SITE_DIR = Path("site")
RUN_IN_DOCS_ENVIRONMENT = "uv run --locked --group docs python .github/scripts/check_docs_build.py"

# Zensical colours its output whether or not it goes to a terminal.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

ZENSICAL_DIAGNOSTIC = re.compile(r"^(?:Warning|Error): ")
# The first line of the box Zensical draws under a diagnostic: `╭─[ index.md:3:5 ]`.
ZENSICAL_LOCATION = re.compile(r"^╭─\[\s*(?P<where>[^\]]+?)\s*\]$")
LOGGED_WARNINGS = (
    # A record printed with its level, as the default build's handler
    # (`WARNING:mkdocs.plugins.griffe:griffe: ...`) and MkDocs (`WARNING -  ...`) print them.
    re.compile(r"^(?:WARNING|ERROR|CRITICAL)\b"),
    # The same records of Griffe and mkdocstrings from a build with no logging handler, such
    # as a command given after --: their logger adapters start each message with the package
    # name of the logger.
    re.compile(r"^(?:griffe|mkdocstrings|mkdocstrings_handlers|mkdocs_autorefs): "),
    # A warning from the warnings module: `path:line: SomeWarning: message`.
    re.compile(r"^\S.*:\d+: [A-Z]\w*Warning: "),
)

TRACEBACK = "Traceback (most recent call last):"
# How Zensical ends the build when --strict stops it on its diagnostics, which the
# verdict lists already.
STRICT_ABORT = "RuntimeError: Aborted because --strict flag is set"

PREFIX = "Docs build gate:"


def find_warnings(log: list[str]) -> list[str]:
    """Return the warnings in a build log, one line each.

    Args:
        log: The build's output, one line per item, colour codes included.

    Returns:
        Each warning line without its colour codes, in log order. A Zensical
        diagnostic is prefixed with the file, line and column it points at.
    """
    lines = [ANSI_ESCAPE.sub("", line).strip() for line in log]
    warnings: list[str] = []
    for index, line in enumerate(lines):
        if ZENSICAL_DIAGNOSTIC.match(line):
            following = lines[index + 1] if index + 1 < len(lines) else ""
            location = ZENSICAL_LOCATION.match(following)
            warnings.append(f"{location['where']}: {line}" if location else line)
        elif any(pattern.match(line) for pattern in LOGGED_WARNINGS):
            warnings.append(line)
    return warnings


def find_errors(log: list[str]) -> list[str]:
    """Return the exception each Python traceback in a build log ends with.

    A traceback runs from its `Traceback (most recent call last):` line through its indented
    lines to the first line that is not indented: the exception. When a plugin raises, Zensical
    prints its own traceback, which ends with `RuntimeError: Python error: <the exception>`,
    then the plugin's, which ends at a blank line with no exception line of its own.

    Args:
        log: The build's output, one line per item, colour codes included.

    Returns:
        Each exception line without its colour codes, in log order, except Zensical's own
        line for a build that --strict stopped.
    """
    errors: list[str] = []
    in_traceback = False
    for raw in log:
        line = ANSI_ESCAPE.sub("", raw).rstrip()
        if line == TRACEBACK:
            in_traceback = True
        elif in_traceback and not line[:1].isspace():
            in_traceback = False
            if line and line != STRICT_ABORT:
                errors.append(line)
    return errors


def file_version(path: Path) -> tuple[int, int] | None:
    """Return the inode and modification time of a file, or None if there is none.

    A build that writes the file anew or over the old one changes one of the two.
    """
    try:
        status = path.stat()
    except OSError:
        return None
    return status.st_ino, status.st_mtime_ns


def stream(process: subprocess.Popen[str]) -> list[str]:
    """Copy the process's output to stdout line by line as it arrives, and return it."""
    log: list[str] = []
    if process.stdout is None:
        msg = "the build's output is not piped"
        raise RuntimeError(msg)
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        log.append(line)
    return log


def gate(command: list[str], site_dir: Path) -> int:
    """Run the build, stream its log, print the verdict and return the exit status."""
    index = site_dir / "index.html"
    before = file_version(index)
    try:
        process = subprocess.Popen(  # noqa: S603 - runs the build command it was given
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        print(f"{PREFIX} the build did not run: could not start {command[0]!r}: {exc}")
        print(f"  Run the gate in the docs environment: {RUN_IN_DOCS_ENVIRONMENT}")
        return 2
    with process:
        log = stream(process)
    returncode = process.wait()

    if returncode < 0:
        print(f"{PREFIX} the build did not run to the end: signal {-returncode} stopped it.")
        return 2
    errors = find_errors(log)
    warnings = find_warnings(log)
    if returncode != 0 or errors or warnings:
        print(f"{PREFIX} failed.")
        if returncode != 0:
            print(f"  The build exited with status {returncode}.")
        if errors:
            print(f"  The build raised {len(errors)} Python error(s):")
            for error in errors:
                print(f"    {error}")
        if warnings:
            print(f"  The build log has {len(warnings)} warning or error line(s):")
            for warning in warnings:
                print(f"    {warning}")
        return 1
    written = file_version(index)
    if written is None or written == before:
        print(
            f"{PREFIX} the build did not run to the end: it exited 0 but did not write "
            f"{index}. Check that site_dir in mkdocs.yml is {site_dir}."
        )
        return 2
    print(f"{PREFIX} passed. The build wrote {site_dir} and logged no warning.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run the gate; return the exit status (0, 1 or 2)."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=DEFAULT_SITE_DIR,
        help="where the build writes the site, site_dir in mkdocs.yml (default: %(default)s)",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help=f"the build command, after -- (default: zensical {shlex.join(ZENSICAL_ARGUMENTS)})",
    )
    args = parser.parse_args(argv)
    command: list[str] = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        if not command:
            if importlib.util.find_spec("zensical") is None:
                print(
                    f"{PREFIX} the build did not run: zensical is not installed for "
                    f"{sys.executable}."
                )
                print(f"  Run the gate in the docs environment: {RUN_IN_DOCS_ENVIRONMENT}")
                return 2
            command = [sys.executable, "-c", ZENSICAL_UNDER_A_LOGGING_HANDLER, *ZENSICAL_ARGUMENTS]
        return gate(command, args.site_dir)
    # A gate that broke has no verdict: exit 1 would read as a docs problem with
    # none listed, and exit 0 as a clean build.
    except Exception:  # noqa: BLE001 - mapped to exit 2 with its traceback
        traceback.print_exc()
        print(f"{PREFIX} the gate itself failed, so there is no result.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
