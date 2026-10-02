"""Offline tests for the deprecation of ``PermitException`` (PER-16331).

permit 4.0 removes ``PermitException``. Until then, every read of the name, from ``permit`` or
from ``permit.exceptions``, issues one DeprecationWarning that names 4.0 and the replacement,
attributed to the line that read it. Code that never names it gets no warning, whatever else it
imports. The class itself is unchanged: ``PermitConnectionError`` still subclasses it, so
``except PermitException`` keeps catching connection errors.

This process imported permit before any test ran, so the tests of a first import run in a fresh
interpreter and report every warning recorded there.
"""

import asyncio
import json
import os
import pickle
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

import aiohttp
import pytest

import permit
from permit import exceptions
from permit.exceptions import PermitConnectionError, PermitError, handle_client_error
from permit.utils.pydantic_version import PYDANTIC_VERSION

ON_PYDANTIC_1 = PYDANTIC_VERSION < (2, 0)

MESSAGE = (
    "PermitException is deprecated and will be removed in permit 4.0; catch "
    "PermitConnectionError instead (in 4.0 it becomes a PermitError)."
)

# The directory that holds the permit package this process imported, so that the fresh
# interpreter imports the same copy whether or not permit is installed.
PERMIT_PARENT = Path(permit.__file__).resolve().parents[1]

# Each way to read the name, as the first line in a fresh interpreter that mentions permit.
FIRST_READS = [
    "from permit import PermitException",
    "from permit.exceptions import PermitException",
    "import permit; permit.PermitException",
    "import permit.exceptions; permit.exceptions.PermitException",
]

CONSUMER = """\
import json
import warnings

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    {first_read}

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

FIRST_READ_LINENO = CONSUMER.splitlines().index("    {first_read}") + 1


def run_in_fresh_interpreter(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        env={**os.environ, "PYTHONPATH": str(PERMIT_PARENT)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def recorded_warnings(caught: list[warnings.WarningMessage]) -> list[tuple[type, str, str, int]]:
    return [(w.category, str(w.message), w.filename, w.lineno) for w in caught]


def read_permit_exception() -> type[Exception]:
    """The class that ``permit.PermitException`` names, read with its warning expected."""
    with pytest.warns(DeprecationWarning, match="PermitException is deprecated"):
        return permit.PermitException  # type: ignore[deprecated]


@pytest.mark.parametrize("first_read", FIRST_READS)
def test_reading_the_name_first_warns_once_at_that_line(tmp_path: Path, first_read: str) -> None:
    consumer = tmp_path / "consumer.py"
    consumer.write_text(CONSUMER.format(first_read=first_read))

    result = run_in_fresh_interpreter(str(consumer))

    assert result.returncode == 0, result.stderr
    records: list[dict[str, Any]] = json.loads(result.stdout)
    # On pydantic 1, importing permit also warns that pydantic 1 is deprecated, on purpose
    # (tests/test_fix_pydantic1_deprecation.py).
    records = [record for record in records if "Support for pydantic 1" not in record["message"]]
    assert records == [
        {
            "category": "DeprecationWarning",
            "message": MESSAGE,
            "filename": str(consumer),
            "lineno": FIRST_READ_LINENO,
        }
    ]


def test_every_read_of_the_name_warns_once_at_its_line(tmp_path: Path) -> None:
    reads = [
        "from permit import PermitException",
        "from permit.exceptions import PermitException",
        "permit.PermitException",
        "permit.exceptions.PermitException",
        "getattr(permit, 'PermitException')",
        "from permit import PermitException",
    ]
    filename = str(tmp_path / "consumer.py")
    code = compile("\n".join(reads), filename, "exec")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        exec(code, {"permit": permit})  # noqa: S102 - the reads under test, as a user writes them

    assert recorded_warnings(caught) == [
        (DeprecationWarning, MESSAGE, filename, lineno) for lineno in range(1, len(reads) + 1)
    ]


@pytest.mark.parametrize(
    "code",
    [
        "import permit",
        "import permit.exceptions",
        "import permit.sync",
        "from permit import *",
        "from permit.exceptions import *",
        "from permit import PermitConnectionError, PermitError",
        "import permit, permit.exceptions; dir(permit); dir(permit.exceptions)",
        "from permit import PermitConnectionError\nclass Mine(PermitConnectionError): pass",
    ],
)
def test_code_that_does_not_name_it_does_not_warn(code: str) -> None:
    options = ["-W", "error"]
    if ON_PYDANTIC_1:
        # importing permit warns on pydantic 1 on purpose; the later -W option takes precedence.
        options += ["-W", "ignore:Support for pydantic 1 is deprecated:DeprecationWarning"]

    result = run_in_fresh_interpreter(*options, "-c", code)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@pytest.mark.parametrize("module", ["permit", "permit.exceptions"])
def test_a_star_import_neither_warns_nor_binds_the_name(module: str) -> None:
    """A star import reads every name it binds, so binding PermitException would warn."""
    namespace: dict[str, object] = {}

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        exec(f"from {module} import *", namespace)  # noqa: S102 - the star import is the subject

    assert "PermitConnectionError" in namespace
    assert "PermitException" not in namespace


def test_dir_still_lists_the_name() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert "PermitException" in dir(permit)
        assert "PermitException" in dir(exceptions)


def test_both_modules_serve_the_same_class() -> None:
    with pytest.warns(DeprecationWarning, match="PermitException is deprecated"):
        from_exceptions = exceptions.PermitException  # type: ignore[deprecated]

    assert read_permit_exception() is from_exceptions
    assert PermitConnectionError.__mro__[1] is from_exceptions


def test_except_permit_exception_still_catches_a_connection_error() -> None:
    """Regression guard, not an endorsement: 4.0 re-parents PermitConnectionError, not 3.x.

    Consumers of 2.x catch connection failures with ``except PermitException``. Moving
    PermitConnectionError under PermitError in 3.x would silently stop that handler from
    catching them.
    """
    permit_exception = read_permit_exception()

    @handle_client_error
    async def send() -> None:
        raise aiohttp.ClientConnectionError

    async def call_as_existing_code_does() -> str:
        try:
            await send()
        except permit_exception:
            return "caught"
        return "not raised"

    assert asyncio.run(call_as_existing_code_does()) == "caught"


def test_the_class_and_its_subclass_are_unchanged() -> None:
    permit_exception = read_permit_exception()
    error = PermitConnectionError("boom")

    assert isinstance(error, permit_exception)
    assert isinstance(error, PermitError)
    assert [f"{cls.__module__}.{cls.__qualname__}" for cls in PermitConnectionError.__mro__] == [
        "permit.exceptions.PermitConnectionError",
        "permit.exceptions.PermitException",
        "permit.exceptions.PermitError",
        "builtins.Exception",
        "builtins.BaseException",
        "builtins.object",
    ]
    assert repr(permit_exception("boom")) == "PermitException('boom')"
    assert repr(error) == "PermitConnectionError('boom')"


def test_a_connection_error_pickles_without_a_warning() -> None:
    error = PermitConnectionError("boom")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - this process pickled it

    assert type(restored) is PermitConnectionError
    assert restored.args == ("boom",)
    assert restored.original_error is None


def test_only_reading_the_name_warns() -> None:
    """Creating, raising, catching or subclassing the class does not warn by itself.

    ``_PermitException`` is the name the SDK itself uses for the class.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(exceptions._PermitException):
            raise exceptions._PermitException

        class Custom(exceptions._PermitException):
            pass

        Custom("boom")
