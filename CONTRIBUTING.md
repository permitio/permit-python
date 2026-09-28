# Contributing

The project is managed with [uv](https://docs.astral.sh/uv/). The uv version is pinned by
`[tool.uv] required-version` in `pyproject.toml`; install exactly that version
(`uv self update <version>`) before starting. A newer uv refuses to run here. An older one
cannot parse the `[tool.uv]` table, warns, and ignores it, including the pin and the 7-day
`exclude-newer` cooldown, which produces a different `uv.lock`.

## Setup

```sh
uv sync                      # .venv with the SDK and the dev tools, exactly as locked in uv.lock
uv run pre-commit install    # lint, format, type-check and uv.lock checks on every commit
```

`uv sync` installs the SDK from this checkout in editable mode, so the tests and scripts
import the working tree's `permit`. `.python-version` selects Python 3.11, the version the
end-to-end CI job runs on. The SDK itself supports Python 3.10 and later.

## Dependencies

- Runtime requirements are `[project].dependencies` in `pyproject.toml`. They are open
  ranges, and the comments there say why each floor and exclusion is what it is.
  `tests/test_offline_regressions.py` and `skills/tests` check those floors.
- Dev tools are exact pins in the `dev` dependency group, which `uv sync` installs by
  default.
- After changing either, run `uv lock` and commit `uv.lock` with the change. The `uv-lock`
  pre-commit hook fails while the two disagree, and CI installs with `uv sync --locked`,
  which refuses a stale lock.
- `uv lock` leaves out releases less than 7 days old (`exclude-newer` in `[tool.uv]`), but
  the dependency audit does not, so it can fail on an advisory whose fix `uv lock` still
  filters out. To take that fix now, add `exclude-newer-package = { <package> = false }`
  under `[tool.uv]`, run `uv lock` and commit both files. Passing
  `--exclude-newer-package` to `uv lock` on the command line is not enough: `uv.lock`
  records the options it was locked with, so `uv lock --check` and `uv sync --locked` then
  reject it. Once the release is 7 days old, remove the entry and run `uv lock` again.

## Running the tests

### Offline tests

Every test that needs credentials, the Permit API or a PDP is marked `e2e`. The rest run
against local mock servers and need no PDP, API key or network access:

```sh
uv run pytest -m "not e2e"
```

### Both pydantic majors

The SDK supports pydantic 1 and 2, and CI runs the suite once per major. Each major is a
dependency group, and both resolutions are in `uv.lock`:

```sh
uv run --group pydantic-v1 pytest -m "not e2e"   # pydantic 1.x
uv run --group pydantic-v2 pytest -m "not e2e"   # pydantic 2.x
```

`uv run` syncs `.venv` to the groups it is given before running the command, so pass the
group every time: a plain `uv run` switches back to the default resolution (pydantic 2.x).

### Other Python versions

```sh
uv run --python 3.14 --group pydantic-v2 pytest -m "not e2e"
```

`--python` rebuilds `.venv` with that interpreter, and the next `uv run` without it
rebuilds `.venv` with the `.python-version` one.

CI's `compatibility` job runs the offline tests on Python 3.10 to 3.14, both at the lowest
versions the runtime requirements allow and at the newest.

### Type checking

`tests/test_typing_surface.py` runs mypy on `tests/type_check/consumer.py` the way a user's
project sees an installed permit, and fails while `permit/_sync_types.pyi` is out of date
(see [Regenerating the sync stubs](#regenerating-the-sync-stubs)). The `mypy` pre-commit
hook type-checks the SDK itself.

### The migration skill's tests

`skills/tests` checks `MIGRATION.md` and the permit-python-3-migration skill against each
other and against the SDK. It runs apart from the SDK's suite, with its own pytest config:

```sh
uv run python -m pytest -c skills/tests/pytest.ini skills/tests
```

See [skills/tests/README.md](skills/tests/README.md).

### The CI scripts' tests

`.github/scripts` holds the dependency audit's report formatter and the schema drift check,
with their tests. They need only pytest and the standard library, and run with their own
pytest config, which turns every warning into an error. The command is the one the
`Audit Script Tests` job runs:

```sh
uv run --only-dev pytest -c .github/scripts/pytest.ini \
  .github/scripts/test_format_audit.py .github/scripts/test_check_schema_drift.py
```

### End-to-end tests

The tests marked `e2e` talk to a real Permit environment through a running PDP. `uv run
pytest` with no arguments runs the whole suite (`testpaths` is `tests/`). CI
(`.github/workflows/test.yml`) creates a scratch environment per run, starts a PDP container
for it, and sets:

- `PDP_API_KEY`: the scratch environment's API key. Every e2e test fails without it.
- `PDP_URL=http://localhost:7766`: the PDP. This is also the default when unset.
- `API_TIER=prod`: sends the SDK's API calls to `https://api.permit.io`.
- `ORG_PDP_API_KEY` and `PROJECT_PDP_API_KEY`: the same key, read by
  `tests/endpoints/test_envs.py`.

Without `API_TIER=prod` (or an explicit `PDP_CONTROL_PLANE`), `tests/conftest.py` sends API
calls to `http://localhost:8000`. To reproduce CI locally with an environment-level API key:

```sh
docker run -d --name permit-pdp -p 7766:7000 -e PDP_API_KEY="$PDP_API_KEY" \
  permitio/pdp-v2:latest
PDP_URL=http://localhost:7766 API_TIER=prod \
  ORG_PDP_API_KEY="$PDP_API_KEY" PROJECT_PDP_API_KEY="$PDP_API_KEY" \
  uv run pytest -s --cache-clear tests/
```

The suite creates and deletes objects in that environment, so use a throwaway one.

## Regenerating the sync stubs

The blocking client, `permit.sync.Permit`, wraps the async classes at runtime, which type
checkers cannot follow. `permit/_sync_types.pyi` declares the blocking signatures for them
and is generated from the async classes. After changing an async API class, regenerate it:

```sh
uv run python scripts/generate_sync_stubs.py
```

## Regenerating the API models

`permit/api/models.py` is generated from the Permit OpenAPI spec, then hand-edited at the top
so the same models work under both pydantic majors. Regenerating overwrites that edit, so it
has to be restored by hand.

1. Regenerate:

   ```sh
   bash scripts/generate_models.sh
   ```

   The script runs the generator through `uvx`, pinned to 0.33.0, the release that produced
   the current file. Its `--exclude-newer` date freezes the generator's dependencies and
   formatters, so an unchanged spec regenerates the same models, and those dependencies do
   not install on Python 3.14, hence `--python 3.11`. The comments in the script explain the
   generator flags, such as `--use-default-kwarg`.

2. Restore the compatibility header. The generator writes a single import line such as:

   ```py
   from pydantic import AnyUrl, BaseModel, EmailStr, Extra, Field, conint, constr
   ```

   Replace it with the header the committed file has, keeping exactly the names the generator
   imported in every branch:

   ```py
   import typing as _typing

   # Private, or permit/__init__.py's `from permit.api.models import *` would export it.
   from ..utils.pydantic_version import PYDANTIC_VERSION as _PYDANTIC_VERSION

   if _typing.TYPE_CHECKING:
       # The v1 API is what runs under either pydantic major, so type-check against it.
       from pydantic.v1 import AnyUrl, BaseModel, Extra, Field, conint, constr

       # pydantic.v1 declares EmailStr as a str subclass, so a type checker would reject
       # a plain str for an email field. At runtime these fields take and hold a plain
       # str; pydantic 2 types its own EmailStr as str for the same reason.
       EmailStr = str
   elif _PYDANTIC_VERSION < (2, 0):
       from pydantic import AnyUrl, BaseModel, EmailStr, Extra, Field, conint, constr
   else:
       from pydantic.v1 import AnyUrl, BaseModel, EmailStr, Extra, Field, conint, constr
   ```

   Without it, the v1-style models do not load under pydantic 2. Keep `PYDANTIC_VERSION`
   imported under the private `_PYDANTIC_VERSION` alias.

3. Re-apply the hand fixes: the entries in `.github/scripts/schema_drift_allowlist.json`
   whose reason says "by hand".

4. Do not run `ruff format` on it: `permit/api/models.py` is excluded from ruff in
   `pyproject.toml` and keeps the generator's formatting, so the diff shows only API changes.

5. Run the schema drift check, the offline tests under both pydantic majors (see above) and
   `uv run pre-commit run --all-files`.

### Schema drift check

`.github/scripts/check_schema_drift.py` runs the same generator with the same flags (a unit
test keeps it equal to `scripts/generate_models.sh`) and compares the result with
`permit/api/models.py` by structure: classes, fields, types, required or optional, defaults,
aliases, `Config.extra` and enum members. A difference that makes the SDK send what the API
rejects, or reject what it returns, fails the check. A class or optional field the SDK lacks
is only reported. That includes a class deleted from `permit/api/models.py`: the schema has
classes no SDK method uses, and a class the SDK does not have cannot change what it sends or
parses. Known differences are listed in `.github/scripts/schema_drift_allowlist.json` with a
one-line reason each, and an entry that no longer matches fails the check until it is
removed.

```sh
uv run python .github/scripts/check_schema_drift.py --models permit/api/models.py \
  --allowlist .github/scripts/schema_drift_allowlist.json
```

It exits 0 (no new failing drift and no stale entry), 1 (new failing drift or a stale entry)
or 2 (the comparison did not run). `.github/workflows/schema-drift.yml` runs it weekly, on
manual dispatch and on pull requests that change `permit/api/models.py`,
`.github/scripts/check_schema_drift.py`, `.github/scripts/schema_drift_allowlist.json` or the
workflow itself.

## Building

```sh
uv build    # sdist and wheel into dist/
```

`dist/` is the only build output; uv's build backend leaves no `build/` or `*.egg-info`
directory behind.

Releasing is done by publishing a GitHub release, which runs
`.github/workflows/python-sdk-publish.yml` (build, then security scan, then PyPI). The release
tag sets the version.
