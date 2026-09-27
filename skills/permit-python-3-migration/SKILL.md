---
name: permit-python-3-migration
description: Upgrade a Python project from permit 2.x (Permit.io's Python SDK, also called permit-python or the permitio SDK) to permit 3.0.0. Use when asked to upgrade or bump permit, permit-python or the permitio Python SDK from 2.x to 3.x; when code breaks after that upgrade (ImportError for ApiKeyLevel or PYDANTIC_VERSION, a coroutine or "event loop is already running" error from permit.sync, resource_relations.list() returning a page, new type errors from permit); or to clear permit's DeprecationWarnings (the flat permit.api methods, pydantic 1 support) before permit 4.0.
---

# permit 2.x to 3.0.0

Scan the project, apply the mechanical edits, bring every judgement call to the user, then
prove the result with the project's own checks.

Bundled resources:

- `scripts/scan.py`: read-only scanner. Standard library only, runs on Python 3.8+, so it works
  before the project moves. Reports each affected site as `path:line`, a change ID, SAFE or
  NEEDS-REVIEW, and a message.
- `references/changes.md`: every change ID with how to detect it, the exact edit, and its
  safety. Read the entry for each ID the scan reports before editing.

## 1. Preflight

Find the project's Python version and its permit and pydantic versions. Run the scan first; its
`summary` collects most of this:

```bash
python3 <this skill's directory>/scripts/scan.py <project root> --json > <scratch dir>/permit-scan.json
```

- Python: `summary.python_pins` (`requires-python`, `python_requires`, `.python-version`,
  Dockerfile `FROM`, CI matrices, tox, mypy `python_version`). Confirm with the interpreter the
  project runs under (`python --version` in its virtualenv or container).
- permit: `summary.permit_requirements` and `summary.permit_locked`, or `pip show permit`.
- pydantic: `summary.pydantic_requirements`, or `pip show pydantic`.

**If the project must keep running on Python 3.8 or 3.9, stop.** permit 3 requires Python 3.10,
and pip on 3.8/3.9 quietly keeps 2.x. Edit nothing; explain [Staying on 2.x](#staying-on-2x) and
that moving to Python 3.10+ comes first.

If permit is already 3.x, skip to step 4 to clear what the scan still reports (usually D1 and D2).

## 2. Read the scan

The JSON has `findings` (`path`, `line`, `change`, `safety`, `message`), `changes` (the IDs
found, with titles), `summary` and `skipped` (files that did not parse). Exit status is 0 whatever
it finds; 2 means a usage error. Group the findings by ID and read those entries in
`references/changes.md`.

## 3. Update the dependencies

- Change every permit requirement (P1) to `permit>=3.0.0,<4`.
- C2 with httpx: the project imports httpx but only got it through permit 2.x. Add
  `httpx>=0.24.1,<1` to its dependencies. For C2 on httpcore, h11, anyio or zipp, first check
  whether another dependency still installs the package (`uv tree --invert --package NAME`,
  `pipdeptree -r -p NAME`); declare it only if nothing does.
- Raise the pins C3 reports to the new floors.
- Regenerate lock files with the project's tool (`uv lock`, `poetry lock`, `pipenv lock`,
  `pip-compile`), install, and check that `python -c "import permit"` works. A requirements file
  compiled by `pip-compile` or `uv pip compile` is a lock too: regenerate it with the command in
  its header; don't edit it.
- Re-scan after regenerating. If a new C2 appears, declare that package in the file the lock is
  compiled from and regenerate again.

## 4. Apply the SAFE edits

Apply every SAFE finding as its message and `references/changes.md` say. Keep the diff to the
edit: no reformatting and no unrelated changes. Re-run the scan; the SAFE findings are gone.

## 5. Bring the NEEDS-REVIEW items to the user

Don't guess. For each NEEDS-REVIEW finding, show `path:line`, the code, what changed in 3.0, and a
recommendation (each entry in `references/changes.md` gives the default). Group sites that share
one decision. Apply what the user approves and leave the rest.

The cases that need a decision most:

- W1: a `None` that 2.x dropped now clears the field. Ask whether clearing was intended.
- A3: a `ContextStore` transform was never applied. Deleting the call keeps behaviour;
  applying the transform changes decisions.
- A2 in async code: recommend switching to the async `permit.Permit` and keeping the `await`;
  dropping the `await` leaves a blocking call in the coroutine. With an untraced client, the
  edit applies only to `permit.sync.Permit`.
- C1: raising the Python floor changes where the project runs.

## 6. Verify

1. Run the project's tests the way it runs them (pytest, tox, nox, make).
2. Run its type checker if it has one. permit is typed now (T1), so new errors can be real bugs
   such as a pydantic 2 method on an SDK model (T2). Fix them; don't add ignores for permit.
3. Run the tests with deprecation warnings as errors, to catch deprecated calls the scan could
   not trace, such as a client passed in from another module:

   ```bash
   python -m pytest -W error::DeprecationWarning -W "ignore:Use PermitError instead:DeprecationWarning"
   ```

   For unittest, pass the same `-W` options to `python -m unittest`. The second filter is
   required: `import permit` warns because `PermitConnectionError` subclasses the deprecated
   `PermitException`, and without the filter every module that imports permit fails to load.
   If other libraries' warnings fail the run, use
   `-W "error:permit.api.:DeprecationWarning"`, which fails only on the flat `permit.api`
   methods. On pydantic 1 also add `-W "ignore:Support for pydantic 1:DeprecationWarning"`
   and report D1. Each warning names its replacement (D2 in `references/changes.md`).
4. Re-run the scan. Only the NEEDS-REVIEW items the user chose to keep should remain.

If mocks, test doubles or recorded requests fail, check A1 (a relations mock must return a
page), A2 (`AsyncMock` doubles of the blocking client's methods become `Mock`) and W2 to W6 (the
requests changed, not the behaviour) in `references/changes.md`.

## 7. Report

- **Changed:** files and edits, grouped by change ID.
- **Needs a human decision:** remaining NEEDS-REVIEW items, each with a recommendation.
- **Verified:** each command run (tests, type checker, deprecation run, final scan) and its
  result. Say what could not be run and why.

## Staying on 2.x

For a project that can't leave Python 3.8/3.9 yet, or can't take 3.0 now. permit 2.8.3 allows
`aiohttp>=3.12.14,<4` and `httpx>=0.24.1,<1`. httpx 0.25.1 and later don't cap anyio; 0.24.x and
0.25.0 reach it through httpcore, which allows anyio below 5.

- **On Python 3.10 or later:** stay on `permit==2.8.3` and add these constraints to the project's
  own requirements or lock file. They clear the advisories permit 3 fixes by raising floors:
  - `aiohttp>=3.14.3` (CVE-2026-69244 and older aiohttp advisories)
  - `anyio>=4.14.2` (CVE-2026-63374)
  - `h11>=0.16.0` (CVE-2025-43859; the resolver then picks httpcore 1.0.9 or later)
  - `pydantic>=1.10.13,<2` or `pydantic>=2.4.2` (CVE-2024-3772)
- **On Python 3.8 or 3.9:** the aiohttp and anyio fixes can't be installed; aiohttp 3.14.3 and
  anyio 4.14.2 both require Python 3.10. `h11>=0.16.0` and the pydantic floor still install.
  The advisories give workarounds: set `AIOHTTP_NO_EXTENSIONS=1`, so aiohttp uses its Python
  parser, which CVE-2026-69244 doesn't affect; and permit never imports httpx or anyio, so
  CVE-2026-63374 concerns only the project's own anyio code (the advisory's workaround: encode
  host names with the `idna` package before connecting). Scanners keep reporting both until the
  project moves to Python 3.10+. permit 2.8.3 itself needs Python 3.9 (its aiohttp floor does);
  on 3.8, pip resolves an older 2.x.
