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

The ruff, mypy and typos hooks run through `uv run --locked`, which syncs `.venv` to `uv.lock`
before running the tool, so the versions in `uv.lock` are the only ones in play; the hooks fail
if `uv.lock` is out of date with `pyproject.toml`. The same checks by hand:

```sh
uv run ruff check              # lint (the rule set is `select = ["ALL"]` minus justified ignores)
uv run ruff format             # format
uv run mypy                    # strict type check of permit/, tests/ and .github/scripts/
uv run typos                   # spelling
```

The SDK is type-checked against both pydantic majors, because it imports pydantic differently
per major. CI runs mypy once more under pydantic 1; do the same locally when touching a pydantic
import (see [Both pydantic majors](#both-pydantic-majors) for why `--no-sync`):

```sh
uv sync --group pydantic-v1 && uv run --no-sync mypy
```

`.python-version` selects Python 3.11, the version CI runs on. The SDK itself supports
Python 3.10 and later.

## Running the tests

### Offline tests

These run against local mock servers and need no PDP, API key or network access:

```sh
uv run pytest \
  tests/test_offline_regressions.py \
  tests/test_fix_enforcement.py \
  tests/test_fix_permissions.py \
  tests/test_fix_relations.py \
  tests/test_fix_serialization.py \
  tests/test_fix_sync.py \
  tests/test_fix_tenants.py
```

### End-to-end tests

Everything else in `tests/` talks to a real Permit environment through a running PDP. `uv run
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

### Both pydantic majors

The SDK supports pydantic v1 and v2, and CI runs the suite once per major. Each major is a
dependency group, and both resolutions are in `uv.lock`:

```sh
uv sync --group pydantic-v1   # pydantic 1.x
uv sync --group pydantic-v2   # pydantic 2.x
```

Run commands in a lane with `uv run --no-sync` (as CI does): a plain `uv run`, and so every
pre-commit hook, syncs `.venv` back to the default resolution (pydantic 2.x) first, as does a
plain `uv sync`.

## Building

```sh
uv build    # sdist and wheel into dist/
```

Releases are built and published by `.github/workflows/python-sdk-publish.yml` when a GitHub
release is published; the release tag sets the version.

## Regenerating the API models

`permit/api/models.py` is generated from the Permit OpenAPI spec, then hand-edited at the top
so the same models work under both pydantic majors. Regenerating overwrites that edit, so it
has to be restored by hand.

1. Regenerate. The generator version is pinned to the one that produced the current file:
   0.33.0 is the last version that emits pydantic v1 models (`pydantic.BaseModel`), and it
   does not run on Python 3.14, hence `--python 3.11`. `--exclude-newer` pins its formatters
   (black, isort) to what was current when the file was last generated, so an unchanged spec
   produces an unchanged file.

   ```sh
   uvx --python 3.11 --exclude-newer 2025-09-18 \
     --from 'datamodel-code-generator[http]==0.33.0' datamodel-codegen \
     --url https://api.permit.io/v2/openapi.json \
     --input-file-type openapi \
     --output permit/api/models.py \
     --output-model-type pydantic.BaseModel \
     --allow-extra-fields \
     --enum-field-as-literal one \
     --use-one-literal-as-default \
     --use-subclass-enum
   ```

2. Restore the compatibility header. The generator writes a single import line such as:

   ```py
   from pydantic import AnyUrl, BaseModel, EmailStr, Extra, Field, conint, constr
   ```

   Replace it with the block below, keeping exactly the names the generator imported in all
   three branches, and add `import typing as _typing` above the generated `from datetime import
   datetime` line:

   ```py
   from permit.utils.pydantic_version import PYDANTIC_VERSION

   if _typing.TYPE_CHECKING:
       # The v1 API is what runs under either pydantic major, so type-check against it.
       from pydantic.v1 import AnyUrl, BaseModel, EmailStr, Extra, Field, conint, constr
   elif PYDANTIC_VERSION < (2, 0):
       from pydantic import AnyUrl, BaseModel, EmailStr, Extra, Field, conint, constr
   else:
       from pydantic.v1 import AnyUrl, BaseModel, EmailStr, Extra, Field, conint, constr
   ```

   Without it, the v1-style models do not load under pydantic 2. The `TYPE_CHECKING` branch
   makes mypy see them as the v1 models they are on both majors; otherwise mypy takes the
   first import it finds and, under pydantic 2, checks every model against the v2 API.
   `typing` is imported under a private alias because `permit/__init__.py` star-imports this
   module: a public `TYPE_CHECKING` or `typing` name would become part of the `permit` namespace.

3. Do not run `ruff format` on it: `permit/api/models.py` is excluded from ruff and typos
   in `pyproject.toml` and keeps the generator's formatting, so the diff shows only API changes.

4. Run the offline tests under both pydantic majors (see above) and `uv run pre-commit run
   --all-files`.
