# Contributing

The project is managed with [uv](https://docs.astral.sh/uv/). CI runs the uv version pinned
as `uv==…` in the `dev` group of `pyproject.toml` (Dependabot keeps it current); install that
version (`uv self update <version>`) before starting, so `uv.lock` comes out the same as in
CI. `[tool.uv] required-version` is only a floor: a uv older than it refuses to run here.
A uv too old to parse the `[tool.uv]` table warns and ignores it, including that floor and
the 7-day `exclude-newer` cooldown, which produces a different `uv.lock`.

## Setup

```sh
uv sync                      # .venv with the SDK and the dev tools, exactly as locked in uv.lock
uv run pre-commit install    # lint, format, type-check and uv.lock checks on every commit
```

`uv sync` installs the SDK from this checkout in editable mode, so the tests and scripts
import the working tree's `permit`. `.python-version` selects Python 3.11, the version the
end-to-end CI jobs run on. The SDK itself supports Python 3.10 and later.

The ruff, mypy and typos hooks run through `uv run --locked`, which syncs `.venv` to `uv.lock`
before running the tool, so the versions in `uv.lock` are the only ones in play; the hooks fail
if `uv.lock` is out of date with `pyproject.toml`. That sync uses the default groups, so a commit
also switches a `.venv` synced with `--group pydantic-v1` back to pydantic 2.x. The same checks
by hand:

```sh
uv run ruff check              # lint (the rule set is `select = ["ALL"]` minus justified ignores)
uv run ruff format             # format
uv run mypy                    # strict type check of every Python file but the generated models
uv run typos                   # spelling
```

The SDK is type-checked against both pydantic majors, because it imports pydantic differently
per major. CI runs mypy once more under pydantic 1; do the same locally when touching a pydantic
import:

```sh
uv run --group pydantic-v1 mypy
```

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

Any warning fails the test that raised it (`filterwarnings` in `[tool.pytest]`), except the
one `import permit` issues on pydantic 1 on purpose. The migration skill's and the CI
scripts' tests do the same with their own configs.

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
hook type-checks the SDK itself, strictly and with the pydantic plugin (see [Setup](#setup)).

### Connection reuse

pytest-httpserver closes each connection after its response, so the tests of how the
clients keep and close their connections (`tests/test_async_session_lifecycle.py` and
`tests/test_sync_lifecycle.py`) use `tests/keepalive_server.py`, a local HTTP/1.1 server
that keeps every connection open and counts the connections it accepted and those that were
closed. The benchmark runs on it too: it times sequential `check()` calls of the async and
the blocking client, and prints how many connections each opened.

```sh
uv run --locked python -m tests.benchmark_connection_reuse --calls 500
```

### The migration skill's tests

`skills/tests` checks `MIGRATION.md` and the permit-python-3-migration skill against each
other and against the SDK. It runs apart from the SDK's suite, with its own pytest config:

```sh
uv run python -m pytest -c skills/tests/pytest.ini skills/tests
```

See [skills/tests/README.md](skills/tests/README.md).

### The CI scripts' tests

`.github/scripts` holds the dependency audit's report formatter, the schema drift check, the
API coverage report and the docs build gate, with their tests, and the tests of the `CI` job,
the job-list check and the local actions' shellcheck (see [CI](#ci)). They need only pytest
and the standard library, and run with their own pytest config, which turns every warning
into an error. `test_ci_checks.py` also runs the bash of those three steps, read from
`test.yml`, so it needs bash, jq, [yq](https://github.com/mikefarah/yq) v4 and shellcheck on
`PATH`, as GitHub's runners have them; `test_check_docs_build.py` reads both workflows with
yq. The command is the one the `Audit Script Tests` job runs:

```sh
uv run --only-dev pytest -c .github/scripts/pytest.ini \
  .github/scripts/test_format_audit.py .github/scripts/test_check_schema_drift.py \
  .github/scripts/test_api_coverage.py .github/scripts/test_ci_checks.py \
  .github/scripts/test_check_docs_build.py
```

### End-to-end tests

The tests marked `e2e` talk to a real Permit environment through a running PDP. `uv run
pytest` with no arguments runs the whole suite (`testpaths` is `tests/`).

`.github/workflows/test.yml` runs the e2e tests in four jobs. Each job creates its own
scratch environment in the CI project and deletes it when the job ends, whether the tests
passed or not:

- `pytest (Pydantic pydantic<2.0.0)` and `pytest (Pydantic pydantic>=2.0.0)`, which the `CI`
  job needs, run the whole suite against a PDP container. Its image is `PINNED_PDP_IMAGE` at
  the top of the workflow: `permitio/pdp-v2` pinned by version and digest, so a new PDP
  release cannot fail `CI`.
- `e2e (latest PDP image)` does not block a pull request: `CI` does not need it. Once both
  `pytest` jobs pass, it runs the whole suite on pydantic 2 against `permitio/pdp-v2:latest`
  and logs the digest `:latest` resolved to. If it fails while `pytest` passes, the newest
  PDP release behaves differently from the pinned one.
- `e2e (cloud PDP)`, the other leg of that job, does not block a pull request either. Once
  both `pytest` jobs pass, it runs `tests/test_cloud_pdp_e2e.py` against the hosted cloud
  PDP, `https://cloudpdp.api.permit.io`, with no container. Its tests create a small RBAC
  policy in the scratch environment, wait for the cloud PDP to apply it, and check the exact
  answers of `check`, `bulk_check`, `get_user_permissions` and `filter_objects`. Three more
  check that `get_user_tenants`, `permit.pdp_api` and the facts methods with
  `proxy_facts_via_pdp` on, whose routes the cloud PDP does not serve, raise the SDK's error
  for its 404. The module runs only against the cloud PDP and skips anywhere else, so this
  job fails if any of its tests is skipped.

The jobs set:

- `PDP_API_KEY`: the scratch environment's API key. Every e2e test fails without it.
- `PDP_URL`: `http://localhost:7766`, the PDP container, or `https://cloudpdp.api.permit.io`
  in `e2e (cloud PDP)`. When it is unset, `tests/test_cloud_pdp_e2e.py` uses the cloud PDP
  and every other test `http://localhost:7766`, or the cloud PDP with `CLOUD_PDP=true`. The
  tests of what only a container PDP serves (`get_user_tenants`, `permit.pdp_api`, and facts
  written with `proxy_facts_via_pdp`) need a PDP container, because the cloud PDP answers 404
  for those routes. They use the `container_pdp` fixture of `tests/conftest.py`, so they skip,
  with the reason, when the PDP they would call is the cloud PDP.
- `API_TIER=prod`: sends the SDK's API calls to `https://api.permit.io`.
- `ORG_PDP_API_KEY` and `PROJECT_PDP_API_KEY`: the same key, read by
  `tests/endpoints/test_envs.py`.
- `PERMIT_API_COVERAGE_RECORD`, in the `pytest` jobs only: where the request recorder writes
  the requests the tests send. The `API Coverage` job reads the e2e tests' requests from
  it (see "API coverage report").

Without `API_TIER=prod` (or an explicit `PDP_CONTROL_PLANE`), `tests/conftest.py` sends API
calls to `http://localhost:8000`. To reproduce the `pytest` jobs locally with an
environment-level API key, on the PDP image they pin:

```sh
PDP_IMAGE=$(grep -Eo 'permitio/pdp-v2:[0-9.]+@sha256:[0-9a-f]{64}' .github/workflows/test.yml)
docker run -d --name permit-pdp -p 7766:7000 -e PDP_API_KEY="$PDP_API_KEY" "$PDP_IMAGE"
PDP_URL=http://localhost:7766 API_TIER=prod \
  ORG_PDP_API_KEY="$PDP_API_KEY" PROJECT_PDP_API_KEY="$PDP_API_KEY" \
  uv run pytest -s --cache-clear tests/
```

Set `PDP_IMAGE=permitio/pdp-v2:latest` instead to reproduce `e2e (latest PDP image)`. The
cloud PDP tests need no container. They send their API calls to `https://api.permit.io`
whatever `API_TIER` is, unless `PDP_CONTROL_PLANE` is set:

```sh
PDP_URL=https://cloudpdp.api.permit.io uv run pytest tests/test_cloud_pdp_e2e.py
```

The suite creates and deletes objects in that environment, so use a throwaway one.

### Moving the PDP pin

Dependabot does not update `PINNED_PDP_IMAGE`. To move it to a new PDP release, first check
that `e2e (latest PDP image)` passed on that release: its `Start the PDP` step logs the
digest `:latest` resolved to. Then set `PINNED_PDP_IMAGE` to
`permitio/pdp-v2:<version>@<digest>`, where `<digest>` is the digest of the release's
multi-arch image index:

```sh
curl -s https://hub.docker.com/v2/repositories/permitio/pdp-v2/tags/<version> | jq -r .digest
```

Docker pulls by the digest; the tag only names it.

Then refresh the PDP spec snapshot the API coverage report reads, from a container of the
new image (see "API coverage report" below). Until then, the `Audit Script Tests` job fails:
a test there checks that `.github/api-specs/pdp.source.json` names the pinned image.

## CI

`.github/workflows/test.yml` holds every check a pull request must pass, and runs on every
pull request and every push to `main`. Its last job, `CI`, is the one check to require: it
needs every other job in the workflow but the advisory ones (see below), and fails unless
each of them succeeded. A job that failed, was cancelled or was skipped fails it, because
GitHub counts a skipped required check as passing. The one exception is `Dependency Review`,
which runs on pull requests only: on a push it is skipped, and `CI` passes.
`Post Audit Comment` runs on every event, posts only on a pull request from a branch of this
repository, and elsewhere succeeds with its steps skipped.

Until the `main` ruleset requires `CI` alone, it requires the check names of six jobs:
`pytest (Pydantic pydantic<2.0.0)`, `pytest (Pydantic pydantic>=2.0.0)`, `pre-commit`,
`Dependency Audit`, `Audit Script Tests` and `Workflow Hardening`. Do not rename those jobs
until then: GitHub leaves a required check that never reports pending, which blocks every
pull request.

To add a job to `test.yml`, do one of these in the same change:

- add its id to the `needs` of the `ci` job, and set `EXPECTED_JOBS` in that job's step to
  the new number of jobs in `needs`;
- or, if it must not block a pull request, add its id to `ADVISORY_JOBS` in the `Check that
  CI needs every job` step of the `Workflow Hardening` job, with a comment saying why.
  `e2e-unpinned-pdp` (`e2e (latest PDP image)` and `e2e (cloud PDP)`) is the only one.

That step fails `Workflow Hardening` when a job is in neither list, when an `ADVISORY_JOBS`
entry is not a job, is listed twice or is also in `needs`, or when `EXPECTED_JOBS` is not
the number of jobs in `needs`. `CI` itself exits 2 when the number of job results it gets is
not `EXPECTED_JOBS`. When you delete a job, remove its id from `needs` and lower
`EXPECTED_JOBS`, or remove it from `ADVISORY_JOBS`.

`.github/workflows/security.yml` is the weekly dependency audit. Every Monday at 09:00 UTC,
and when started with Run workflow, it runs the same audit as the `Dependency Audit` job
(`.github/actions/dependency-audit`) and posts the result to Slack. It gates no pull
request. Neither do the schema drift check (`schema-drift.yml`) and the weekly API coverage
run (`api-coverage.yml`).

actionlint shellchecks the bash in workflows but not in the local actions under
`.github/actions`, so the `Shellcheck the local actions` step of `Workflow Hardening` does
that, with the options actionlint uses.

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

4. Do not run `ruff format` on it: `permit/api/models.py` is excluded from ruff and typos
   in `pyproject.toml` and keeps the generator's formatting, so the diff shows only API changes.

5. Add each new model to `__all__` in `permit/__init__.py`, and remove each deleted one:
   `from permit import *` binds only the names `__all__` lists, and type checkers treat only
   those as exported. `tests/test_fix_permit_exception_deprecation.py` fails until the list
   matches. A name the models import for their own use, such as one from `typing`, goes in that
   test's `NOT_EXPORTED` instead.

6. Run the schema drift check, the offline tests under both pydantic majors (see above) and
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

## API coverage report

`.github/scripts/api_coverage.py` reports which operations of the Permit API the SDK covers
(PER-16337). An operation counts as covered when an offline test sends a request that
matches it: `tests/api_coverage_recorder.py`, a pytest plugin that `tests/conftest.py`
loads, writes down the method and path of every request the tests send when it is given a
record file, and does nothing otherwise. The report matches each request to an operation
of two specs: the control plane's (`https://api.permit.io/v2/openapi.json`) and the
container PDP's (`/openapi.json` on the PDP image `PINNED_PDP_IMAGE` names). It reads them
from the operation inventories committed under `.github/api-specs/`, each with a
`.source.json` file that says where and when it was taken. Request and response shapes are
the schema drift check's job (above), not this one's.

```sh
uv run pytest -q -m "not e2e" --api-coverage-record /tmp/offline.jsonl
uv run python .github/scripts/api_coverage.py report \
  --spec control-plane=.github/api-specs/control-plane.json \
  --spec pdp=.github/api-specs/pdp.json \
  --allowlist .github/scripts/api_coverage_allowlist.json \
  --record /tmp/offline.jsonl
```

An operation no offline test sends a request to must be in
`.github/scripts/api_coverage_allowlist.json`, with the stage the spec gives it (`GA`,
`EAP` or `deprecated`), a status and one reason:

- `excluded`: the SDK does not mean to cover it.
- `deferred`: planned, with the ticket that plans it.
- `untested`: an SDK method sends it, but no offline test does. The reason names the method.

A request that matches no operation in either spec is SDK-only, and needs an `sdk_only`
entry: `undocumented` (the SDK calls a route the spec does not list, with a ticket) or
`test-only` (a made-up route a test sends to). An entry's path may use `{name}` for a path
segment.

The report exits 1 on a GA operation that is neither covered nor allowlisted, on a stale
entry (its operation is covered now, or is not in the spec, or no request matches an
`sdk_only` entry), on an entry whose stage no longer matches the spec, and on an SDK-only
request no entry explains. EAP and deprecated operations that are not allowlisted are
listed, but do not fail it. It exits 2 when it did not run: a spec it cannot read or that
lists too few operations, an invalid allowlist, or a record that is missing, comes from a
session that failed or did not finish, or holds too few requests.

So when an offline test starts sending an allowlisted operation's request (the wire test
of a new method for a `deferred` operation, or a new test for an `untested` one), its
entry has to go in the same change. A method's wire test with `proxy_facts_via_pdp` on may
also send a `/facts/...` request that the PDP forwards to the control plane but does not
list in its spec; that request needs an `undocumented` `sdk_only` entry. Every public
method of the facts APIs has such a test: `tests/facts_methods.py` pins the request each one
sends with the proxy on, the tests of the PDP's waits and of the cloud PDP's 404 run on each,
and a new facts method fails `test_every_public_facts_method_has_a_case` until it has a case
there.

A method's wire test is in the offline module of its API, for example
`tests/test_schema_offline.py` (resources, their attributes, relations and roles, roles,
condition sets and condition set rules), `tests/test_facts_operations_offline.py` (the bulk
and single-object facts methods with the proxy off and on, and user invites) or
`tests/test_projects_environments_offline.py`. Such a module calls the method on the async
and the blocking client with the helpers of `tests/utils.py` (`invoke`, `sent_headers`,
`ApiError`), and checks the request, its headers, what the response parses into and the
error an API error response raises. The schema and the projects and environments modules,
and `tests/test_fix_resource_actions.py`, fail `test_every_public_method_has_a_case` until
every public method of their APIs has a case; the facts operations module holds only the
user invite methods to that, with `test_every_public_user_invites_method_has_a_case`. Add a
new method's wire test there in the same change, so that its operation never needs an
`untested` entry.

CI runs the report in two places:

- The `API Coverage` job in `.github/workflows/test.yml`, on every pull request, against
  the committed snapshots. The `pytest` jobs record their requests too, and the report's
  end-to-end column shows which operations their e2e tests got a 2xx or 3xx answer from,
  or "not run" when there is no record.
- `.github/workflows/api-coverage.yml`, weekly and on manual dispatch, against the live
  control-plane spec. It lists how the live spec differs from the committed snapshot,
  fails on an untriaged GA operation, and posts to Slack when it fails.

When the live spec changes, refresh the control-plane snapshot. The weekly run's
`api-coverage-live` artifact holds a ready one under `live/`; or take it yourself:

```sh
curl -fsS -o /tmp/openapi.json https://api.permit.io/v2/openapi.json
uv run python .github/scripts/api_coverage.py snapshot control-plane /tmp/openapi.json \
  --source https://api.permit.io/v2/openapi.json
```

For the PDP, start a container of the pinned image with an environment's API key, as in
"End-to-end tests" (it answers 503 until it has loaded that environment's configuration),
then:

```sh
curl -fsS -o /tmp/pdp-openapi.json http://localhost:7766/openapi.json
uv run python .github/scripts/api_coverage.py snapshot pdp /tmp/pdp-openapi.json \
  --source "GET /openapi.json on a container of $PDP_IMAGE (PINNED_PDP_IMAGE in .github/workflows/test.yml)"
```

Commit the snapshot together with the allowlist entries for whatever it adds.

## The API reference site

<https://permitio.github.io/permit-python/> is the SDK's API reference, generated from its
docstrings and type annotations by [Zensical](https://zensical.org/) and mkdocstrings.
`mkdocs.yml` configures it, the pages are under `docs/`, and the tools are exact pins in the
`docs` dependency group. Guides stay on docs.permit.io, which every page links to.

Build it the way CI does, into `site/` (gitignored):

```sh
uv run --locked --group docs python .github/scripts/check_docs_build.py
```

That runs `zensical build --strict --clean` under the docs build gate, which the `docs` job
in `.github/workflows/test.yml` runs too, and which fails on any warning in the build log and
on any broken link in the site:

- `--strict` fails the build on a broken link to a page, a missing anchor, a cross-reference
  that resolves to nothing, or a `:::` line that names no object.
- `--strict` checks only the links of the pages under `docs/`, before they are rendered. The
  links in docstrings, and in `README.md` and `MIGRATION.md`, which the home page and
  "Upgrading to 3.0" include, come later, so the gate reads the built site: each relative
  link must reach a page or file of the site, and its `#anchor` an id on that page. It lists
  each broken one with the built page that has it, such as
  `reference/api/roles/index.html: ../../nope/: reference/nope/index.html does not exist`.
- What the build logs while it renders the pages does not fail it: Griffe's docstring
  warnings, such as an `Args:` entry for a parameter the function does not have, and any
  warning from mkdocstrings, a Markdown extension or the Griffe extension. The build still
  ends with "No issues found". The gate runs Zensical under a logging handler that prints each
  of those records with its level, as
  `WARNING:mkdocs.plugins.griffe:griffe: <file>:<line>: <message>`, and fails on those lines,
  so fix every one.
- `--clean` empties Zensical's page cache (`.cache/`, gitignored). Without it, a build renders
  only the pages whose sources changed, and does not print the warnings of the pages it
  skips.

The gate exits 0 when the build passed, 1 when it failed, logged a warning or left a broken
link (it lists each one at the end), and 2 when the build did not run to the end, so there is
no result: `zensical` is not installed, a signal stopped the build, or the build wrote no
`site/index.html`. An error from `uv run` itself, such as an out-of-date `uv.lock`, comes
before the gate starts, so no verdict follows it; CI installs the docs group in a step of its
own, which fails instead.

To preview the site while editing, run
`uv run --locked --group docs zensical serve` and open <http://localhost:8000>. It rebuilds on
every change to `docs/`, the SDK, the Griffe extension, `README.md` or `MIGRATION.md`.

Docstrings are Google style, and their examples are fenced code blocks (```` ```python ````),
which render as code. `scripts/docs_griffe_extension.py` makes the pages show what a type
checker sees: the blocking classes come from `permit/_sync_types.pyi`, a method decorated as
deprecated gets a `deprecated` label and its decorator's message, a `@contextmanager` method
returns an `AbstractContextManager` of what it yields, and a pydantic field's
`Field(description=...)` becomes its docstring. `tests/test_docs_griffe_extension.py`, part
of the offline suite, checks it.

- **A page.** Write it under `docs/` and add it to `nav` in `mkdocs.yml`. A line
  `::: permit.module.Name` renders that object. The home page and "Upgrading to 3.0" include
  `README.md` and `MIGRATION.md`: edit those files, and link from them with absolute URLs,
  which work on GitHub, PyPI and the site alike.
- **An API class.** Copy a page under `docs/reference/api/`: it documents the async class,
  then its blocking twin from `permit.api.sync_api_client`. Add the page to `nav` and to the
  table in `docs/reference/api/index.md`.
- **A model.** `docs/reference/models.md` lists the models of `permit.api.models` that a
  public method takes or returns. When a method starts or stops using one,
  `tests/test_docs_griffe_extension.py` fails and names it; add it to, or remove it from,
  the alphabetical `members` list on that page.

Pull requests build the site but never deploy it. `.github/workflows/docs-deploy.yml`
(Deploy Docs) builds it through the same gate and deploys it to GitHub Pages when a release
is published, or a prerelease is changed to a release (a prerelease itself does not deploy),
and when started by hand with Run workflow. The site has one version, the latest release's.
The `github-pages` environment accepts deploys from `main` and from `v*` tags only, so a
release tagged `X.Y.Z` without the `v` publishes to PyPI but cannot deploy the site; run
Deploy Docs from `main` instead. Deploy Docs does not wait for the PyPI upload
([Releasing](#releasing)): if the publish workflow fails, the site documents a version PyPI
does not have until the release is fixed.

## Building

```sh
uv build    # sdist and wheel into dist/
```

`dist/` is the only build output; uv's build backend leaves no `build/` or `*.egg-info`
directory behind.

## Releasing

Publishing a GitHub release runs `.github/workflows/python-sdk-publish.yml`. It runs on
`published` only, so saving a draft publishes nothing. The release tag sets the version:
`vX.Y.Z` or `X.Y.Z`, optionally with a PEP 440 suffix such as `rc1` or `.post1`. Any other
tag, including the hyphenated `X.Y.Z-rc.N` form older releases used, fails the build.

The workflow has three jobs, each of which runs only if the one before it passed:

1. **Build distribution** builds the sdist and the wheel with the uv version and checksum
   pinned in the workflow. It fails if either one lacks `permit/py.typed` or
   `permit/_sync_types.pyi`, or ships a package other than `permit`: the wheel may hold only
   `permit/` and its `.dist-info`, and the sdist no directory but `permit/`. Pull requests
   run the same check: one leg of the `compatibility` job in `.github/workflows/test.yml`
   builds both files and checks them with an identical script.
2. **Security Gate** scans the runtime dependency trees with `.github/scripts/audit-deps.sh`
   and fails on any fixable HIGH or CRITICAL advisory. The report is kept as the
   `release-dependency-audit` artifact for 90 days.
3. **Publish to PyPI** uploads the two files with PyPI trusted publishing, so the job needs
   no PyPI token. PyPI accepts the upload because the `permit` project on pypi.org lists
   repository `permitio/permit-python`, workflow `python-sdk-publish.yml` and environment
   `pypi` as a trusted publisher. Renaming the workflow file or the environment needs the
   same change on pypi.org first, or the next release cannot upload. PyPI does not check
   which branch or tag the job ran from, so the `pypi` environment's deployment rules
   (Settings, Environments) are what keep a branch that edits the workflow from uploading.

None of the jobs uses the Actions cache, and each has a timeout.
