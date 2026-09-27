# permit 2.x to 3.0.0: change catalogue

Every change a permit 2.x to 3.0.0 upgrade can touch, by stable ID. `scripts/scan.py` reports
sites with these IDs. Each entry says how to detect the change, the exact edit, and whether the
edit is **SAFE** (apply it as written) or **NEEDS-REVIEW** (the right edit depends on intent: show
the site to the user with the recommendation, and apply what they choose).

## Contents

- [P1. The permit requirement](#p1-the-permit-requirement)
- Compatibility: [C1. Python 3.10 or later](#c1-python-310-or-later) ·
  [C2. httpx is no longer installed with permit](#c2-httpx-is-no-longer-installed-with-permit) ·
  [C3. Higher dependency floors](#c3-higher-dependency-floors)
- Typing: [T1. permit ships type information](#t1-permit-ships-type-information) ·
  [T2. pydantic 2 methods on SDK models](#t2-pydantic-2-methods-on-sdk-models) ·
  [T3. The mypy plugin](#t3-the-mypy-plugin)
- API: [A1](#a1-resource_relationslist-returns-a-page) · [A2](#a2-three-permitsyncpermit-methods-are-synchronous) ·
  [A3](#a3-removed-symbols) · [A4](#a4-audit-log-models-accept-what-the-api-returns) ·
  [A5](#a5-relationship-tuple-and-api-key-models-accept-what-the-api-returns) ·
  [A6](#a6-other-names-no-longer-importable)
- Wire behaviour: [W1](#w1-an-explicit-none-is-sent-as-null) · [W2](#w2-usersassign_role-and-unassign_role-omit-unset-fields) ·
  [W3](#w3-elementslogin_as-sends-hyphenated-uuids) · [W4](#w4-a-3xx-response-raises) ·
  [W5](#w5-authorization-bearer) · [W6](#w6-the-deprecated-assign_role-and-unassign_role-use-the-users-route)
- Deprecations, removed in 4.0: [D1. pydantic 1 support](#d1-pydantic-1-support-is-deprecated) ·
  [D2. The flat permit.api methods](#d2-the-flat-permitapi-methods-are-deprecated)
- [Bug fixes that change results](#bug-fixes-that-change-results) (no edit)
- [What the scan cannot see](#what-the-scan-cannot-see)

### P1. The permit requirement

- Detect: `permit` in requirements\*.txt, pyproject.toml (PEP 621, Poetry, dependency groups),
  setup.py, setup.cfg or Pipfile with a spec that allows 2.x or excludes 3.x; a lock file
  (poetry.lock, uv.lock, pdm.lock, Pipfile.lock, or a requirements file compiled by `pip-compile`
  or `uv pip compile`, recognised by its header or `# via` lines) that pins permit below 3.
- Edit: `permit>=3.0.0,<4`. Regenerate the lock file with the project's own tool (`uv lock`,
  `poetry lock`, `pipenv lock`, `pip-compile`, or the command in a compiled file's header); never
  edit a lock by hand. **SAFE.** A direct URL or unparseable spec is **NEEDS-REVIEW**.

## Compatibility

### C1. Python 3.10 or later

permit 3.0.0 declares `python_requires>=3.10`. It can't support less: aiohttp 3.14.3 is the only
release that fixes CVE-2026-69244, and it requires Python 3.10. On 3.8 or 3.9, `pip install -U permit`
quietly keeps 2.x.

- Detect: `requires-python`, Poetry `python`, `python_requires`, classifiers, `.python-version`,
  `runtime.txt`, `.tool-versions`, `Dockerfile` `FROM python:3.x`, CI matrices (GitHub Actions,
  GitLab, CircleCI, Travis, Azure, Bitbucket, tox), mypy `python_version`, pyright `pythonVersion`.
- Edit: raise the pin to 3.10 or later. **NEEDS-REVIEW**: it changes which Pythons the project
  supports and where it deploys. If the project must keep running on 3.8 or 3.9, stop and use the
  stay-on-2.x path in SKILL.md.

### C2. httpx is no longer installed with permit

permit 2.x declared `httpx` and `zipp`, and httpx brought `httpcore`, `h11`, `anyio`,
`certifi`, `sniffio` (with httpx before 0.28 and older anyio releases) and `exceptiongroup` (on
Python 3.10). permit never imported them. 3.0.0 declares neither httpx nor zipp, so none of them
is installed with it. `idna` and `typing-extensions` still are.

- Detect: an import of one of these packages in a project that doesn't declare it. Pins in a
  compiled requirements file are not declarations: `httpx==0.28.1  # via permit` disappears when
  the lock is regenerated.
- Edit for httpx: add `httpx>=0.24.1,<1` (the range permit 2.x required) to the project's
  dependencies. **SAFE.**
- Edit for the others: another dependency may still install them (Starlette and FastAPI depend
  on anyio, requests on certifi). Check with `uv tree --invert --package NAME`,
  `pipdeptree -r -p NAME` or `pip show NAME` (Required-by), and declare the package only if
  nothing else brings it. **NEEDS-REVIEW.**

### C3. Higher dependency floors

| Package | permit 2.8.3 | permit 3.0.0 |
| --- | --- | --- |
| `aiohttp` | `>=3.12.14,<4` | `>=3.14.3,<4` |
| `pydantic` | `>=1.10.7` | `>=1.10.18,<2` or `>=2.4.2` on Python 3.10-3.12; `>=1.10.18,<2` or `>=2.8.0` on 3.13; `>=1.10.25,<2` or `>=2.13` on 3.14 |
| `typing-extensions` | `>=4.5.0,<5` | `>=4.14.0,<5` |
| `loguru` | `>=0.7.0,<1` | `>=0.7.3,<1` |
| `httpx`, `zipp` | required | not required (C2) |

pydantic 2.0 to 2.4.1 are excluded on every Python.

- Detect: a pin of one of these packages that allows no version at or above the floor.
- Edit: raise the pin to the floor or later, within the same major. **SAFE.** Moving pydantic
  from 1 to 2 is D1, not C3.

## Typing

### T1. permit ships type information

permit 3.0.0 ships `py.typed` (PEP 561), so type checkers now check calls into it instead of
treating it as untyped.

- Detect: `ignore_missing_imports` or `follow_imports = skip` for `permit` / `permit.*` in mypy
  configuration; `# type: ignore` or `# pyright: ignore` on a line that imports permit.
- Edit: remove permit from the override (the whole section if permit is its only module) and
  remove the ignore comment. **SAFE** for the settings and for a bare ignore or one limited to
  import codes (`import-untyped`, `import`, `reportMissingTypeStubs`, ...). **NEEDS-REVIEW** when
  the ignore also lists other codes, such as `attr-defined`: drop only the import codes. Then run
  the type checker: genuine errors in the project's code may surface. Fix them; don't restore
  the ignore.

### T2. pydantic 2 methods on SDK models

The SDK's models are pydantic v1 models at runtime on both pydantic majors, and are now typed that
way. pydantic 2 methods on them fail type checking. They also always failed at runtime with
`AttributeError`, so any such call is already a bug.

| pydantic 2 | Use on SDK models |
| --- | --- |
| `.model_dump(...)` | `.dict(...)` |
| `.model_dump_json(...)` | `.json(...)` |
| `Model.model_validate(obj)` | `Model.parse_obj(obj)` |
| `Model.model_validate_json(s)` | `Model.parse_raw(s)` |
| `.model_copy(update=..., deep=...)` | `.copy(update=..., deep=...)` |
| `Model.model_json_schema()` | `Model.schema()` |
| `.model_fields_set` | `.__fields_set__` |
| `Model.model_fields` | `Model.__fields__` (values are `ModelField`, not `FieldInfo`) |

- Detect: these methods on a class imported from permit, on a value built from one, on the
  result of a permit API call, or on a name annotated with an SDK model (`user: UserRead`,
  `Optional[UserRead]`). The type checker finds the rest.
- Edit: the rename in the table. **SAFE** when only keywords both versions share are passed
  (`include`, `exclude`, `by_alias`, `exclude_unset`, `exclude_defaults`, `exclude_none`;
  `update`, `deep` for copy). **NEEDS-REVIEW** otherwise: `mode="json"` becomes
  `json.loads(model.json())`, and `model_fields` / `model_config` hold different objects.

### T3. The mypy plugin

No plugin is needed to type-check calls into permit. mypy users on pydantic 2 who want plugin
checking of the SDK's models add `pydantic.v1.mypy`; `pydantic.mypy` does not recognise v1 models.
Both can be listed: `plugins = pydantic.mypy, pydantic.v1.mypy`. No edit is required, and the
scan does not report T3.

## API

### A1. resource_relations.list() returns a page

`permit.api.resource_relations.list()` returns `PaginatedResultRelationRead`. Read `.data` for the
relations and `.total_count` for the total. This is a bug fix: the API always returned a page, so
every 2.x call raised `ValidationError: value is not a valid list`. No working code depends on the
old return type.

- Detect: `.resource_relations.list(` whose result is not read through `.data`, `.total_count` or
  `.page_count`.
- Edit: `relations = (await permit.api.resource_relations.list("doc")).data`. **NEEDS-REVIEW**:
  the call never worked, so look at what the code around it expected (a `try` around it, a
  fallback path) before choosing the edit. Tests that mock `GET .../resources/{key}/relations`
  with a JSON list, or stub `resource_relations.list` to return a list, must return the page
  instead: `{"data": [...], "total_count": n, "page_count": 1}` or a
  `PaginatedResultRelationRead`.

### A2. Three permit.sync.Permit methods are synchronous

On the blocking client `permit.sync.Permit`, `authorized_users()`, `get_user_permissions()` and
`filter_objects()` return their result, like `check()` and `bulk_check()`. The async
`permit.Permit` still needs `await`. This is a bug fix: in 2.x these three stayed `async def`, so
calling one returned a coroutine, and awaiting it raised
`RuntimeError: This event loop is already running`. No working code depends on the old behaviour.

- Detect: `await client.<method>(...)`; the call passed to `asyncio.run()`,
  `run_until_complete()`, `gather()`, `create_task()` and similar; an `AsyncMock` that stands in
  for one of the three methods (`patch(..., new_callable=AsyncMock)`,
  `monkeypatch.setattr(client, "authorized_users", AsyncMock(...))`, an assignment) in a project
  that uses the blocking client.
- Edit, by form:
  - `asyncio.run(client.<method>(...))` or `loop.run_until_complete(...)`: call the method
    directly. This is sync code, so nothing else changes. **SAFE** when `client` is traced to
    `permit.sync.Permit`.
  - `await client.<method>(...)`, or the call passed to `gather()`, `create_task()` and the other
    helpers that run inside a loop: this is async code, where the blocking call blocks the event
    loop while it waits. Recommend switching that code to the async `permit.Permit` and keeping
    the `await`; the alternative is dropping the `await` and accepting a blocking call.
    **NEEDS-REVIEW.**
  - A receiver not traced to either client: the async `permit.Permit` still needs the `await`.
    **NEEDS-REVIEW.**
  - Test doubles: in 2.x these methods returned coroutines, so tests that stubbed them used
    `AsyncMock`. For the blocking client, replace the `AsyncMock` with `Mock` (or `MagicMock`)
    and keep its `return_value`; an `AsyncMock` now hands the code a coroutine.
    **NEEDS-REVIEW**: check that the double replaces the blocking client's method, not the async
    client's.

### A3. Removed symbols

| Removed | What to do | Safety |
| --- | --- | --- |
| `permit.api.context.ApiKeyLevel` | `ApiKeyAccessLevel`, same members and values | SAFE |
| `permit.enforcement.interfaces.JWT` | `str` (it was an alias) | SAFE |
| `ContextStore.register_transform()` and `ContextStore.transform()` | A registered transform was never applied, so the call did nothing. Delete it. If the transform's effect is wanted, apply it to the context passed to `check()`, which changes decisions | NEEDS-REVIEW |
| `permit.utils.context.ContextTransform` | `Callable[[Dict[str, Any]], Dict[str, Any]]` if still needed | NEEDS-REVIEW |
| `permit.api.elements.LoginAsErrorMessages` | Define the strings in the project: `"User not found"`, `"Tenant not found"`, `"Invalid user permission level"`, `"Forbidden access"` | NEEDS-REVIEW |
| `permit.enforcement.interfaces.OpaResult` | Nothing returned it. Define `class OpaResult(BaseModel): allow: bool` in the project if used | NEEDS-REVIEW |

- Detect: imports of these names, attribute access through a permit module alias,
  `.register_transform(` in a file that imports permit, `.transform(` on a `ContextStore`.

### A4. Audit-log models accept what the API returns

`pdp_config_id` on `AuditLogModel` and `DetailedAuditLogModel` is `Optional[UUID]`, and
`DetailedAuditLogModel.objects` is optional: it is `None` when the API sends `null`, and the
field's default, an empty dict `{}` rather than an `AuditLogObjectsModel`, when the log has no
`objects`. `Engine.GENERIC` and `GenericEngineDecisionLog` are new. This is a bug fix: the old
models raised `ValidationError` on logs without a `pdp_config_id` or `objects` and on
GENERIC-engine logs. No SDK method returns these models.

- Detect: `.pdp_config_id.<attr>` in a file that imports the models, unless guarded by
  `is not None`, `isinstance()` or a truthiness check; `DetailedAuditLogModel`'s
  `.objects.<attr>` unless guarded by `isinstance()` or a truthiness check (`is not None` lets
  `{}` through); an `Engine` import in a file that never mentions `GENERIC`.
- Edit: check `pdp_config_id` for `None` before use. Read `objects` only after
  `isinstance(log.objects, AuditLogObjectsModel)`. Handle `Engine.GENERIC` wherever the code
  branches on every engine. **NEEDS-REVIEW.**

### A5. Relationship-tuple and API-key models accept what the API returns

`object_id` on `RelationshipTupleRead` and `RelationshipTupleDetailedRead` is `Optional[UUID]`;
`subject_details`, `relation_details`, `object_details` and `tenant_details` on
`RelationshipTupleDetailedRead` are optional; `APIKeyOwnerType` gains `nats_pdp_config`. This is a
bug fix: `relationship_tuples.list()` and `create()` raised `ValidationError` on a tuple whose
`object_id` is null or absent (a tuple on every resource of the object's type), and
`environments.get_api_key()` raised on a key owned by `nats_pdp_config`.

- Detect: `.object_id.<attr>` or `.<x>_details.<attr>` in a file that uses
  `relationship_tuples` or imports the models, unless guarded; an `APIKeyOwnerType` import in a
  file that never mentions `nats_pdp_config`.
- Edit: check for `None` before use; handle the new owner type. **NEEDS-REVIEW.**

### A6. Other names no longer importable

These names are gone in 3.0.0 but are not in the release notes' list of removed symbols.

| Name | Use instead | Safety |
| --- | --- | --- |
| `permit.PYDANTIC_VERSION`, `permit.api.models.PYDANTIC_VERSION`, `permit.pdp_api.base.PYDANTIC_VERSION` | `from permit.utils.pydantic_version import PYDANTIC_VERSION` | SAFE |
| `permit.enforcement.enforcer.set_if_not_none` | copy the helper: `if v is not None: d[k] = v` | SAFE |
| `permit.pdp_api.base.T`, `TModel`, `TData` | define your own `TypeVar` | SAFE |
| `BaseModel`, `Extra`, `Field` from `permit.pdp_api.base` | `pydantic.v1` | SAFE |
| `Callable`, `List`, `TypeVar` from `permit.pdp_api.base`, `permit.utils.context`, `permit.api.resource_relations` | `typing` | SAFE |
| `Enum` from `permit.api.elements` | `enum` | SAFE |
| `RoleAssignmentsApi` from `permit.api.deprecated` | `permit.api.role_assignments` | SAFE |
| `iscoroutinefunction` from `permit.utils.sync` | `inspect` | SAFE |

## Wire behaviour

Same API, different bytes. No edit is needed unless the project asserts on permit's requests (HTTP
mocks, recorded cassettes, proxies).

### W1. An explicit None is sent as null

A model field explicitly set to `None` is sent as `null`, so an update can clear a field. In 2.x it
was dropped: `users.update(key, UserUpdate(email=None))` sent `{}` and did nothing. Fields never set
are still omitted. A dict passed where a method takes a model is validated into the model first,
so `users.update(key, {"email": None})` changes the same way.

- Detect: a permit request model (`*Create`, `*Update`, `*Remove`, `*Delete`, `*Replace`) built with
  a keyword that is `None`, `x if c else None`, `d.get(k)`, `getattr(o, n, None)` or a parameter
  typed `Optional` or defaulting to `None`, unless guarded by `is not None`; a dict literal with
  such a value passed to a `permit.api` method.
- Edit: pass the field only when it has a value, unless clearing it is intended. **NEEDS-REVIEW**:
  in 2.x such a call left the field unchanged, and in 3.0 it clears it.

### W2. users.assign_role() and unassign_role() omit unset fields

They match `role_assignments.assign()`. The API treats an omitted field and `null` the same for
these fields. No edit; not reported.

### W3. elements.login_as() sends hyphenated UUIDs

Given `UUID` objects, `elements.login_as()` sends the canonical hyphenated form instead of 32-char
hex. The API accepts both and resolves them to the same record. No edit; not reported.

### W4. A 3xx response raises

A 3xx response raises instead of being treated as success. No 3xx is reachable on any path the
SDK calls, and aiohttp follows redirects anyway. No edit; not reported.

### W5. Authorization: Bearer

Every `Authorization` header uses `Bearer`, not `bearer`. The scheme is case-insensitive
(RFC 7235), so servers don't care.

- Detect: a string starting with `bearer ` in a file that imports permit.
- Edit: if it matches permit's header in a test or mock, change it to `Bearer`.
  **NEEDS-REVIEW.**

### W6. The deprecated assign_role() and unassign_role() use the users route

`permit.api.assign_role()` / `unassign_role()` forward to `permit.api.users.assign_role()` /
`unassign_role()`, so they send `POST` / `DELETE /users/{user}/roles` instead of
`/role_assignments`. Same effect. Replacing them (D2) makes the same request. Update HTTP mocks
that expect `/role_assignments`. Not reported separately.

## Deprecations, removed in 4.0

Both still work in 3.x and warn with a `DeprecationWarning` that says what to use instead.

### D1. pydantic 1 support is deprecated

On pydantic 1, `import permit` warns once: "Support for pydantic 1 is deprecated and will be
removed in permit 4.0. Upgrade to pydantic 2."

- Detect: a pydantic requirement that allows no 2.x; with such a pin, pytest configuration that
  turns warnings into errors (`filterwarnings = error`, `-W error`).
- Edit: plan the move to pydantic 2. Until then, add the filter
  `ignore:Support for pydantic 1:DeprecationWarning`. Under pydantic 2 the SDK's models come from
  `pydantic.v1`, so invalid input raises `pydantic.v1.ValidationError`; catching
  `pydantic.v1.ValidationError` works under both majors. **NEEDS-REVIEW.**

### D2. The flat permit.api methods are deprecated

Each of the 21 flat methods on `permit.api` warns with its replacement, for example
"permit.api.get_user() is deprecated and will be removed in permit 4.0; use
permit.api.users.get() instead." The warning points at the line that made the call on both
clients. `permit` below stands for the client, whatever the variable is called.

| Deprecated | Replacement | Keyword changes |
| --- | --- | --- |
| `permit.api.get_user()` | `permit.api.users.get()` | |
| `permit.api.get_role()` | `permit.api.roles.get()` | |
| `permit.api.get_tenant()` | `permit.api.tenants.get()` | |
| `permit.api.get_assigned_roles()` | `permit.api.users.get_assigned_roles()` | `user_key=` to `user=`, `tenant_key=` to `tenant=` |
| `permit.api.get_resource()` | `permit.api.resources.get()` | |
| `permit.api.list_roles()` | `permit.api.roles.list()` | |
| `permit.api.sync_user()` | `permit.api.users.sync()` | |
| `permit.api.delete_user()` | `permit.api.users.delete()` | |
| `permit.api.list_tenants()` | `permit.api.tenants.list()` | |
| `permit.api.create_tenant()` | `permit.api.tenants.create()` | `tenant=` to `tenant_data=` |
| `permit.api.update_tenant()` | `permit.api.tenants.update()` | `tenant=` to `tenant_data=` |
| `permit.api.delete_tenant()` | `permit.api.tenants.delete()` | |
| `permit.api.create_role()` | `permit.api.roles.create()` | `role=` to `role_data=` |
| `permit.api.update_role()` | `permit.api.roles.update()` | `role=` to `role_data=` |
| `permit.api.assign_role()` | `permit.api.users.assign_role()` | three arguments become one: `{"user": u, "role": r, "tenant": t}` |
| `permit.api.unassign_role()` | `permit.api.users.unassign_role()` | three arguments become one: `{"user": u, "role": r, "tenant": t}` |
| `permit.api.delete_role()` | `permit.api.roles.delete()` | |
| `permit.api.create_resource()` | `permit.api.resources.create()` | `resource=` to `resource_data=` |
| `permit.api.update_resource()` | `permit.api.resources.update()` | `resource=` to `resource_data=` |
| `permit.api.delete_resource()` | `permit.api.resources.delete()` | |
| `permit.api.elements_login_as()` | `permit.elements.login_as()` | |

Positional arguments keep their order, and each replacement returns what the deprecated method
returned.

- Detect: `<client>.api.<method>(`, `<handle>.<method>(` where `handle = client.api`, and
  `<name>.<method>(` on an untraced name ending in `api` in a file that imports permit.
- Edit: the replacement, with keyword renames. **SAFE** when the receiver is traced to a permit
  client and there is no `*args` / `**kwargs`. **NEEDS-REVIEW** when the receiver is not traced
  (it may be another library's `.api`). The scan follows Python's scoping: a parameter, local,
  loop or comprehension variable is not the module-level client of the same name, and a name
  also bound to something other than a permit client is not traced.
- The message text changed from 2.x ("use permit.api.users.get() instead"). A warning filter
  written for the old text (a pytest `filterwarnings` or `-W` entry, or a string in Python code,
  whose message starts `use permit.api`) no longer matches anything. Detect those too: delete
  them once the calls are migrated, or match `permit\.api\.\w+\(\) is deprecated` instead.
  **NEEDS-REVIEW.**

## Bug fixes that change results

No edit, but tests that pinned the old results may change:

- `bulk_check()` honours a per-check `context`, and `filter_objects()` passes the caller's
  context through. Context-dependent (ABAC) checks were evaluated against an empty context.
- `UserInput` accepts `first_name` / `last_name` (snake_case), which were silently dropped from
  every check.
- A PDP 401/403 is reported with its status code and body instead of "cannot connect to the PDP".
- `permit.pdp_api.*` calls honour `pdp_timeout`.
- The blocking client works when called inside a running event loop; 2.x raised
  `RuntimeError: This event loop is already running`.
- `users.sync()` no longer removes `key` from the caller's dict.

## What the scan cannot see

- Clients passed in from other modules: an untraced receiver makes D2 and A2 NEEDS-REVIEW, and
  T2 unreported. Run the tests with deprecation warnings as errors (SKILL.md, step 6).
- Values that are `None` only at runtime (W1), such as `**kwargs` or a dict built elsewhere.
- Code that turns SDK objects into strings: `str(t.object_id)` gives `"None"` (A5).
- HTTP mocks and recorded requests (W2 to W6): they fail in the test run.
