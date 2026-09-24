"""Offline tests for the pydantic 1 deprecation warning (PER-16236).

permit 4.0 drops pydantic 1. Until then, importing permit on pydantic 1 issues one
DeprecationWarning that names 4.0 and says what to do, attributed to the line that imported
permit. On pydantic 2 it issues none.

This process imported permit before any test ran, so each test imports it in a fresh
interpreter and reports every warning recorded there.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import permit
from permit.utils.pydantic_version import PYDANTIC_VERSION

ON_PYDANTIC_1 = PYDANTIC_VERSION < (2, 0)

# The directory that holds the permit package this process imported, so that the fresh
# interpreter imports the same copy whether or not permit is installed.
PERMIT_PARENT = Path(permit.__file__).resolve().parents[1]

# Every permit import runs permit/__init__.py first, whichever module it names.
FIRST_IMPORTS = [
    "import permit",
    "from permit.sync import Permit",
    "import permit.utils.pydantic_version",
]

CONSUMER = """\
import json
import warnings

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    {first_import}
    import permit
    import permit.sync
    from permit import Permit

records = [
    {{
        "category": w.category.__name__,
        "message": str(w.message),
        "filename": w.filename,
        "lineno": w.lineno,
    }}
    for w in caught
]
print(json.dumps(records))
"""

FIRST_IMPORT_LINENO = CONSUMER.splitlines().index("    {first_import}") + 1


def pydantic_1_warnings_on_import(consumer: Path, first_import: str) -> list[dict]:
    """Run a script that imports permit in a fresh interpreter, recording every warning.

    Returns the recorded warnings whose message mentions pydantic 1, of any category.
    """
    consumer.write_text(CONSUMER.format(first_import=first_import))
    result = subprocess.run(
        [sys.executable, str(consumer)],
        env={**os.environ, "PYTHONPATH": str(PERMIT_PARENT)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [record for record in json.loads(result.stdout) if "pydantic 1" in record["message"]]


@pytest.mark.skipif(not ON_PYDANTIC_1, reason="pydantic 2 is installed")
@pytest.mark.parametrize("first_import", FIRST_IMPORTS)
def test_importing_permit_on_pydantic_1_warns_once_at_the_import(tmp_path: Path, first_import: str):
    consumer = tmp_path / "consumer.py"

    warned = pydantic_1_warnings_on_import(consumer, first_import)

    assert len(warned) == 1, warned
    [warning] = warned
    assert warning["category"] == "DeprecationWarning"
    assert "removed in permit 4.0" in warning["message"]
    assert "Upgrade to pydantic 2" in warning["message"]
    assert Path(warning["filename"]).resolve() == consumer.resolve()
    assert warning["lineno"] == FIRST_IMPORT_LINENO


@pytest.mark.skipif(ON_PYDANTIC_1, reason="pydantic 1 is installed")
@pytest.mark.parametrize("first_import", FIRST_IMPORTS)
def test_importing_permit_on_pydantic_2_does_not_warn(tmp_path: Path, first_import: str):
    warned = pydantic_1_warnings_on_import(tmp_path / "consumer.py", first_import)

    assert warned == []
