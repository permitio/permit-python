"""The connection reuse benchmark (PER-16344) runs, and counts one connection per client.

The benchmark runs in an interpreter of its own, since it turns the SDK's logging off.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_benchmark_reports_one_connection_per_client() -> None:
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("PYTHONWARNINGS", "PYTHONDEVMODE")
    }

    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-W",
            "ignore:Support for pydantic 1 is deprecated:DeprecationWarning",
            "-m",
            "tests.benchmark_connection_reuse",
            "--calls",
            "5",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert (result.returncode, result.stderr) == (0, "")
    header, *rows = result.stdout.splitlines()[1:]
    assert header.split()[:3] == ["client", "calls", "connections"]
    assert [row.split()[:3] for row in rows] == [["async", "5", "1"], ["sync", "5", "1"]]
