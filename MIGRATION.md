# Upgrading from permit 2.x to 3.0.0

permit 3.0.0 is a major release. It raises the minimum Python to 3.10, raises the dependency
floors to versions without known vulnerabilities, ships type information, and fixes several
methods that could never have worked. Most projects need only the dependency changes. This guide
lists every breaking change, who it affects, and what to do.

Each change has an ID (C1, A2, ...). The same IDs are used by the
[migration skill](skills/permit-python-3-migration/), which can do the upgrade for you with an AI
agent: see [Migrate with an AI agent](#migrate-with-an-ai-agent).

## Contents

- [Who must act](#who-must-act)
- [Before you upgrade](#before-you-upgrade)
- [Compatibility](#compatibility): C1-C3
- [API](#api): A1-A6
- [Wire behaviour](#wire-behaviour): W1-W6
- [Typing](#typing): T1-T3
- [Deprecations (to be removed in 4.0)](#deprecations-to-be-removed-in-40): D1-D2
- [Other fixes you may notice](#other-fixes-you-may-notice)
- [Staying on 2.x for now](#staying-on-2x-for-now)
- [Migrate with an AI agent](#migrate-with-an-ai-agent)

## Who must act

Everyone who upgrades needs:

- **Python 3.10 or later** (C1). On Python 3.8 or 3.9, `pip install -U permit` keeps 2.x without
  an error. See [Staying on 2.x for now](#staying-on-2x-for-now).
- **The new dependency floors** (C3):

  | Package | permit 2.8.3 | permit 3.0.0 |
  | --- | --- | --- |
  | `aiohttp` | `>=3.12.14,<4` | `>=3.14.3,<4` |
  | `pydantic` | `>=1.10.7` | `>=1.10.18,<2` or `>=2.4.2` on Python 3.10-3.12; `>=1.10.18,<2` or `>=2.8.0` on 3.13; `>=1.10.25,<2` or `>=2.13` on 3.14 |
  | `typing-extensions` | `>=4.5.0,<5` | `>=4.14.0,<5` |
  | `loguru` | `>=0.7.0,<1` | `>=0.7.3,<1` |
  | `httpx` | `>=0.24.1,<1` | not required (C2) |
  | `zipp` | `>=3.19.1` | not required |

Code changes are needed only if you:

- import `httpx`, `certifi`, `anyio` or another package C2 lists without declaring it (C2);
- type-check your code (T1-T3);
- call `resource_relations.list()` (A1), or `authorized_users()`, `get_user_permissions()` or
  `filter_objects()` on the blocking `permit.sync.Permit` (A2);
- import a removed name (A3, A6);
- read audit logs, relationship tuples or API keys (A4, A5);
- pass `None` for a field in a create, sync or update call, as a model field or a dict value (W1);
- assert on the exact requests permit sends, in HTTP mocks or recorded fixtures (W2-W6).

The deprecations (D1, D2) keep working in 3.x and warn.

## Before you upgrade

- [ ] Every place the project runs uses Python 3.10 or later: `requires-python`, Docker images,
      CI matrices, `.python-version` (C1).
- [ ] If your code imports `httpx`, `certifi`, `anyio` or another package C2 lists, it declares
      it itself (C2).
- [ ] No pin holds `aiohttp`, `pydantic`, `typing-extensions` or `loguru` below the new floors (C3).
- [ ] You know whether you're on pydantic 1 or 2 (D1).
- [ ] Optional: list what the upgrade touches with the scanner. It is read-only, needs only the
      standard library and runs on Python 3.8+, so it works before you move. It ships with the
      migration skill, not with the permit package: install the skill first (see
      [Migrate with an AI agent](#migrate-with-an-ai-agent)), then run
      `python3 .claude/skills/permit-python-3-migration/scripts/scan.py .` from your project's
      root.
- [ ] Change the requirement (P1), reinstall, and run your tests and type checker.

### P1. The permit requirement

```diff
- permit>=2.8,<3
+ permit>=3.0.0,<4
```

Then regenerate your lock file (`uv lock`, `poetry lock`, `pipenv lock`, `pip-compile`). A
requirements file compiled by `pip-compile` or `uv pip compile` is a lock too: regenerate it
rather than editing it. A regenerated lock no longer lists `httpx` and the packages that came with
it, so declare the ones your code imports first (C2).

## Compatibility

### C1. Python 3.10 or later

- **What changed:** permit 3.0.0 requires Python 3.10 (`python_requires>=3.10`). This can't be
  avoided: aiohttp 3.14.3, the first release that fixes CVE-2026-69244, requires 3.10.
  Python 3.8 was already unsupported in practice, since the old aiohttp floor needed 3.9.
- **Who is affected:** projects on Python 3.8 or 3.9. pip on those versions quietly keeps the
  old, vulnerable permit.
- **What to do:** move to Python 3.10 or later, or see
  [Staying on 2.x for now](#staying-on-2x-for-now).

```diff
  [project]
- requires-python = ">=3.8"
+ requires-python = ">=3.10"
```

### C2. httpx is no longer installed with permit

- **What changed:** permit no longer depends on `httpx` or `zipp`, so neither is installed with
  it, and nor are the packages that came only through httpx: `httpcore`, `h11`, `anyio`,
  `certifi`, `sniffio` (with httpx releases before 0.28 and older anyio releases) and
  `exceptiongroup` (on Python 3.10). The SDK never imported any of them.
- **Who is affected:** code that imports one of them but relied on permit to install it, such as
  `import httpx`, or `ssl.create_default_context(cafile=certifi.where())`.
- **What to do:** declare it yourself. `httpx>=0.24.1,<1` is the range permit 2.x required. For
  the others, check first whether another dependency still installs them (FastAPI and Starlette
  depend on anyio, requests on certifi).

```diff
  permit>=3.0.0,<4
+ httpx>=0.24.1,<1
```

### C3. Higher dependency floors

- **What changed:** the floors in the table under [Who must act](#who-must-act). The old floors
  either no longer install or import cleanly on the Pythons the SDK supports, or carry known
  advisories:
  - pydantic 2.0 to 2.4.1 are excluded on every Python. Under pydantic 2 the SDK validates emails
    with the `pydantic.v1` copy bundled in pydantic, and only 2.4.2 and later bundle one fixed
    for CVE-2024-3772. pydantic 1.10.18 is the first 1.10 release without about 2,400
    import-time warnings on Python 3.13.
  - On Python 3.13, pydantic 2.4.2 to 2.7.x have no `pydantic-core` wheels; on 3.14, earlier
    releases crash on `import permit`.
  - typing-extensions releases before 4.6 break `import permit` on Python 3.12 and later, releases
    before 4.12 break it on 3.13 and later, and 4.12-4.13 lose `TypedDict` keys on 3.14.
  - loguru releases before 0.7.3 warn on 3.14 about an asyncio API that Python 3.16 removes.
- **Who is affected:** projects that pin one of these packages below its floor.
- **What to do:** raise the pin.

```diff
- aiohttp==3.12.14
+ aiohttp>=3.14.3,<4
```

Breaking change 4 in the release notes, the typed package, is covered under [Typing](#typing).

## API

### A1. resource_relations.list() returns a page

- **What changed:** `permit.api.resource_relations.list()` returns `PaginatedResultRelationRead`.
  The relations are in `.data`, the total in `.total_count`.
- **This is a bug fix. The method could not work before it.** The API always returned a
  paginated `{"data": [...], ...}` envelope, and 2.x declared `List[RelationRead]`, so every call
  raised `ValidationError: value is not a valid list`. No working code depends on the old type.
- **Who is affected:** code that calls `resource_relations.list()`, and tests that mock its
  response as a plain list.
- **What to do:** read `.data`. Make mocks of `GET .../resources/{key}/relations` return the page,
  `{"data": [...], "total_count": n, "page_count": 1}`.

```diff
- relations = await permit.api.resource_relations.list("document")
+ relations = (await permit.api.resource_relations.list("document")).data
```

### A2. Three permit.sync.Permit methods are synchronous

- **What changed:** on the blocking client, `permit.sync.Permit`, the methods
  `authorized_users()`, `get_user_permissions()` and `filter_objects()` return their result
  directly, like `check()` and `bulk_check()`. The async `permit.Permit` is unchanged and still
  needs `await`.
- **This is a bug fix. These methods could not work before it.** In 2.x the blocking client
  inherited all three unchanged from the async class, so calling one without `await` returned a
  coroutine instead of a result, and awaiting it, or passing it to `asyncio.run()`, raised
  `RuntimeError: This event loop is already running`. No working code depends on the old
  behaviour.
- **Who is affected:** code that calls these three methods on `permit.sync.Permit`, and tests
  that replace them with `AsyncMock`.
- **What to do:**
  - In synchronous code, call the method directly, without `await` or `asyncio.run()`.
  - In `async` code, prefer the async `permit.Permit` and keep the `await`. Dropping the `await`
    works too, but the blocking call then blocks the event loop while it waits.
  - In tests, replace `AsyncMock` doubles of these methods on the blocking client with `Mock`
    (or `MagicMock`), keeping their `return_value`. An `AsyncMock` now hands your code a
    coroutine.

```diff
  from permit.sync import Permit

  permit = Permit(token="...")
- users = asyncio.run(permit.authorized_users("read", "document:1"))
+ users = permit.authorized_users("read", "document:1")
```

### A3. Removed symbols

- **What changed:** these names are removed:
  - `ContextStore.register_transform()`, `ContextStore.transform()` and `ContextTransform`.
    The SDK never called `transform()`, so a registered transform never affected a check.
    `transform()` applied the registered functions only when your own code called it.
  - `ApiKeyLevel`, a deprecated alias of `ApiKeyAccessLevel`.
  - `LoginAsErrorMessages`, `OpaResult` and the `JWT` alias. None of them had a caller.
- **Who is affected:** code that imports them.
- **What to do:**
  - `ApiKeyLevel`: use `ApiKeyAccessLevel` from `permit.api.context`. It has the same members.
  - `JWT`: use `str`.
  - `register_transform()`: delete the call; no check ever ran the transform, so deleting it
    changes no decision. If you want its effect, apply it to the context you pass to `check()`,
    and expect decisions to change.
  - `transform()`: call the functions you registered on the context yourself.
  - `LoginAsErrorMessages` and `OpaResult`: define what you need in your own code. The messages
    were `"User not found"`, `"Tenant not found"`, `"Invalid user permission level"` and
    `"Forbidden access"`; `OpaResult` was a model with one field, `allow: bool`.

```diff
- from permit.api.context import ApiKeyLevel
+ from permit.api.context import ApiKeyAccessLevel
```

### A4. Audit-log models accept what the API returns

- **What changed:** `pdp_config_id` on `AuditLogModel` and `DetailedAuditLogModel` is
  `Optional[UUID]`, and `DetailedAuditLogModel.objects` is optional. `objects` is `None` when the
  API sends `null`, and an empty dict, `{}`, when the log has no `objects` at all: that is the
  field's default, and it is not an `AuditLogObjectsModel`. `Engine.GENERIC` and
  `GenericEngineDecisionLog` are new.
- **This is a bug fix.** The API returns logs without a `pdp_config_id` or `objects`, and logs
  from the GENERIC engine; the old models rejected them with a `ValidationError`. No SDK method
  returns these models.
- **Who is affected:** code that parses audit logs with these models, and type-checked code that
  treats `pdp_config_id` as a plain `UUID`.
- **What to do:** check `pdp_config_id` for `None`. Check `objects` with
  `isinstance(log.objects, AuditLogObjectsModel)`, not `is not None`, which lets `{}` through.
  Handle `Engine.GENERIC` where you branch on the engine.

```diff
- config_id = log.pdp_config_id.hex
- user = log.objects.user_object
+ config_id = log.pdp_config_id.hex if log.pdp_config_id is not None else None
+ user = log.objects.user_object if isinstance(log.objects, AuditLogObjectsModel) else None
```

### A5. Relationship-tuple and API-key models accept what the API returns

- **What changed:** `object_id` on `RelationshipTupleRead` and `RelationshipTupleDetailedRead` is
  `Optional[UUID]`; `subject_details`, `relation_details`, `object_details` and `tenant_details`
  on `RelationshipTupleDetailedRead` are optional. `APIKeyOwnerType` gains `nats_pdp_config`.
- **This is a bug fix.** `relationship_tuples.list()` and `create()` raised `ValidationError` on a
  tuple whose `object_id` is null or absent, which the API documents as a tuple on every resource
  of the object's type. `environments.get_api_key()` raised on a key owned by
  `nats_pdp_config`.
- **Who is affected:** code that reads these attributes. Type checkers will ask for a `None`
  check.
- **What to do:** check for `None` before using them.

```diff
- ids = [t.object_id.hex for t in tuples]
+ ids = [t.object_id.hex for t in tuples if t.object_id is not None]
```

### A6. Other names no longer importable

- **What changed:** a few names that 2.x exposed only incidentally are gone. They are not in the
  release notes' list of removed symbols. The one most likely to be in use is
  `permit.PYDANTIC_VERSION`, which permit 2.x itself imported that way.
- **Who is affected:** code that imports one of them.
- **What to do:**

  | Name | Use instead |
  | --- | --- |
  | `PYDANTIC_VERSION` from `permit`, `permit.api.models` or `permit.pdp_api.base` | `permit.utils.pydantic_version.PYDANTIC_VERSION` |
  | `permit.enforcement.enforcer.set_if_not_none` | a copy of the helper in your code |
  | `T`, `TModel`, `TData`, `BaseModel`, `Extra`, `Field`, `Callable`, `TypeVar` from `permit.pdp_api.base` | your own `TypeVar`; `pydantic.v1`; `typing` |
  | `Callable`, `List` from `permit.utils.context`; `List` from `permit.api.resource_relations` | `typing` |
  | `Enum` from `permit.api.elements` | `enum` |
  | `RoleAssignmentsApi` from `permit.api.deprecated` | `permit.api.role_assignments` |
  | `iscoroutinefunction` from `permit.utils.sync` | `inspect` |

```diff
- from permit import PYDANTIC_VERSION
+ from permit.utils.pydantic_version import PYDANTIC_VERSION
```

## Wire behaviour

Same API, different bytes on the wire. Each change was checked against the API's request
definitions. Only W1 changes what the API does; the others matter only if you assert on the
requests permit sends.

### W1. An explicit None is sent as null

- **What changed:** a field you explicitly set to `None` is sent as `null`, so an update can clear
  a field. Fields you never set are still omitted.
- **Who is affected:** code that passes `None` for a field it doesn't mean to change, in a create,
  sync or update call. In 2.x, `exclude_none` dropped it: `users.update(key, UserUpdate(email=None))`
  sent `{}` and did nothing. In 3.0 it clears the email. A dict passed to a method that takes a
  model is validated into the model first, so `{"email": None}` behaves the same way. That
  includes `users.sync()`: `users.sync({"key": k, "first_name": u.first_name})` with
  `first_name` of `None` now sends `"first_name": null` where 2.x left the key out.
- **What to do:** pass a field only when it has a value, unless you mean to clear it.

```diff
- await permit.api.users.update(key, UserUpdate(first_name=first_name, last_name=last_name))
+ changes = {"first_name": first_name, "last_name": last_name}
+ await permit.api.users.update(key, UserUpdate(**{k: v for k, v in changes.items() if v is not None}))
```

### W2. users.assign_role() and unassign_role() omit unset fields

- **What changed:** `users.assign_role()` and `users.unassign_role()` leave out fields you didn't
  set, matching `role_assignments.assign()`.
- **Who is affected:** nobody, unless you assert on the request body. The API treats an omitted
  field and `null` the same for these fields.
- **What to do:** nothing.

### W3. elements.login_as() sends hyphenated UUIDs

- **What changed:** given `UUID` objects, `elements.login_as()` sends the canonical hyphenated form
  instead of 32-character hex.
- **Who is affected:** nobody, unless you assert on the request body. The API accepts both
  spellings and resolves them to the same record.
- **What to do:** nothing.

### W4. A 3xx response raises

- **What changed:** a 3xx response raises instead of being treated as success.
- **Who is affected:** nobody in practice. No 3xx is reachable on any path the SDK calls, and
  aiohttp follows redirects anyway.
- **What to do:** nothing.

### W5. Authorization: Bearer

- **What changed:** every `Authorization` header uses `Bearer`, not `bearer`.
- **Who is affected:** tests or proxies that match the header exactly. The scheme is
  case-insensitive (RFC 7235), so servers accept both.
- **What to do:** update exact matches.

```diff
- assert request.headers["Authorization"] == f"bearer {token}"
+ assert request.headers["Authorization"] == f"Bearer {token}"
```

### W6. The deprecated assign_role() and unassign_role() use the users route

- **What changed:** the deprecated `permit.api.assign_role()` and `unassign_role()` forward to
  `permit.api.users.assign_role()` and `unassign_role()`, so they send the request those methods
  send (`/users/{user}/roles`) instead of `/role_assignments`. Both have the same effect.
- **Who is affected:** HTTP mocks that expect `/role_assignments` from these calls.
- **What to do:** replace the calls (D2), which sends the same request, and update the mocks.

## Typing

### T1. permit ships type information

- **What changed:** `permit` is a typed package (PEP 561 `py.typed`). Type checkers used to skip
  it with `import-untyped`; now they check calls into it.
- **Who is affected:** projects that run mypy, pyright or another type checker. Genuine type
  errors in your code may now surface. Model constructors are typed by their fields, so a nested
  model field takes a model instance: `ResourceCreate(key="doc", name="Doc", actions={"read": {}})`
  runs, but a type checker rejects the nested dict.
- **What to do:** drop the settings that hid permit, and fix what the checker reports. For a
  nested field, build the nested model (`actions={"read": ActionBlockEditable()}`), or pass the
  whole payload to the API method as a dict, which methods that take a model accept.

```diff
- [[tool.mypy.overrides]]
- module = ["permit", "permit.*"]
- ignore_missing_imports = true
```

```diff
- from permit import Permit  # type: ignore[import-untyped]
+ from permit import Permit
```

### T2. pydantic 2 methods on SDK models

- **What changed:** the SDK's models are typed as the pydantic v1 models they have always been at
  runtime, on both pydantic majors. pydantic 2 methods such as `.model_dump()` on an SDK model now
  fail type checking.
- **Who is affected:** code that calls pydantic 2 methods on SDK models. Those calls already
  failed at runtime with `AttributeError`.
- **What to do:** use the pydantic v1 names: `.dict()`, `.json()`, `.parse_obj()`,
  `.parse_raw()`, `.copy()`, `.schema()`, `.__fields__`, `.__fields_set__`.

```diff
  user = await permit.api.users.get("user-1")
- data = user.model_dump()
+ data = user.dict()
```

### T3. The mypy plugin

- **What changed:** nothing you must act on. No plugin is needed to type-check calls into permit.
- **Who is affected:** mypy users on pydantic 2 who want plugin checking of the SDK's models.
  `pydantic.mypy` does not recognise the SDK's v1 models.
- **What to do:** if you want it, add the `pydantic.v1.mypy` plugin. It can sit next to
  `pydantic.mypy`, which keeps checking your own pydantic 2 models:

```ini
[mypy]
plugins = pydantic.mypy, pydantic.v1.mypy
```

## Deprecations (to be removed in 4.0)

permit 4.0 is a future major release, and it will remove both of these. Both still work in 3.x
and warn with a `DeprecationWarning` that says what to use instead.

### D1. pydantic 1 support is deprecated

- **What changed:** on pydantic 1, `import permit` warns once: "Support for pydantic 1 is
  deprecated and will be removed in permit 4.0. Upgrade to pydantic 2."
- **Who is affected:** projects on pydantic 1. A project that runs its tests with warnings as
  errors fails on `import permit` until it adds a filter.
- **What to do:** upgrade to pydantic 2. The SDK's models then come from `pydantic.v1`, so their
  methods stay the same, but invalid input raises `pydantic.v1.ValidationError` rather than
  `pydantic.ValidationError`. Catching `pydantic.v1.ValidationError` works under both majors.
  Until you upgrade, the filter `ignore:Support for pydantic 1:DeprecationWarning` silences the
  warning.

### D2. The flat permit.api methods are deprecated

- **What changed:** the 21 flat methods on `permit.api`, such as `permit.api.get_user()`, warn
  with their replacement: "permit.api.get_user() is deprecated and will be removed in permit 4.0;
  use permit.api.users.get() instead." The text differs from 2.x's ("use permit.api.users.get()
  instead"), so warning filters that match the old text need updating.
- **Who is affected:** code that calls them, on either client.
- **What to do:** call the replacement. Positional arguments keep their order, and each
  replacement returns what the deprecated method returned. `permit` below stands for your client.

| Deprecated | Replacement | Keyword changes |
| --- | --- | --- |
| `permit.api.get_user()` | `permit.api.users.get()` | |
| `permit.api.get_role()` | `permit.api.roles.get()` | |
| `permit.api.get_tenant()` | `permit.api.tenants.get()` | |
| `permit.api.get_assigned_roles()` | `permit.api.users.get_assigned_roles()` | `user_key=` becomes `user=`, `tenant_key=` becomes `tenant=` |
| `permit.api.get_resource()` | `permit.api.resources.get()` | |
| `permit.api.list_roles()` | `permit.api.roles.list()` | |
| `permit.api.sync_user()` | `permit.api.users.sync()` | |
| `permit.api.delete_user()` | `permit.api.users.delete()` | |
| `permit.api.list_tenants()` | `permit.api.tenants.list()` | |
| `permit.api.create_tenant()` | `permit.api.tenants.create()` | `tenant=` becomes `tenant_data=` |
| `permit.api.update_tenant()` | `permit.api.tenants.update()` | `tenant=` becomes `tenant_data=` |
| `permit.api.delete_tenant()` | `permit.api.tenants.delete()` | |
| `permit.api.create_role()` | `permit.api.roles.create()` | `role=` becomes `role_data=` |
| `permit.api.update_role()` | `permit.api.roles.update()` | `role=` becomes `role_data=` |
| `permit.api.assign_role()` | `permit.api.users.assign_role()` | the three arguments become one assignment (below) |
| `permit.api.unassign_role()` | `permit.api.users.unassign_role()` | the three arguments become one assignment (below) |
| `permit.api.delete_role()` | `permit.api.roles.delete()` | |
| `permit.api.create_resource()` | `permit.api.resources.create()` | `resource=` becomes `resource_data=` |
| `permit.api.update_resource()` | `permit.api.resources.update()` | `resource=` becomes `resource_data=` |
| `permit.api.delete_resource()` | `permit.api.resources.delete()` | |
| `permit.api.elements_login_as()` | `permit.elements.login_as()` | |

```diff
- user = await permit.api.get_user("user-1")
- await permit.api.assign_role("user-1", "editor", "default")
+ user = await permit.api.users.get("user-1")
+ await permit.api.users.assign_role({"user": "user-1", "role": "editor", "tenant": "default"})
```

### Surfacing and silencing the warnings

Both clients issue the warning at the line that made the call. Python shows it by default only
when that line is in `__main__`, such as the script you run; pytest lists it in its warnings
summary.

- **To see them everywhere:** `python -W default::DeprecationWarning ...` or
  `PYTHONWARNINGS=default::DeprecationWarning`.
- **To fail on them**, which finds every deprecated call your tests reach, and raises before the
  request is sent:

  ```bash
  python -m pytest -W error::DeprecationWarning
  ```

  It also fails on each line that imports `PermitException`, or reads `permit.PermitException`
  or `permit.exceptions.PermitException`, as that line runs (an `except` clause reads it only
  when an exception reaches it). permit 4.0 removes `PermitException`: catch
  `PermitConnectionError` instead. `from permit import *` does not bind `PermitException`, so a
  handler for it after a star import raises `NameError` when an exception reaches it. permit
  2.7.0 to 3.0.0 warn on `import permit` itself ("Use PermitError instead"), from inside the
  SDK; on those, add `-W "ignore:Use PermitError instead:DeprecationWarning"`. To fail on
  permit's flat methods only, use `-W "error:permit.api.:DeprecationWarning"`.
- **To silence them** while you migrate, add filters for the messages:

  ```ini
  # pytest.ini
  [pytest]
  filterwarnings =
      ignore:permit\.api\.\w+\(\) is deprecated:DeprecationWarning
      ignore:Support for pydantic 1:DeprecationWarning
      ignore:PermitException is deprecated:DeprecationWarning
  ```

  In code: `warnings.filterwarnings("ignore", message=r"permit\.api\.\w+\(\) is deprecated", category=DeprecationWarning)`.

## Other fixes you may notice

These need no code change unless your code worked around the old behaviour, but results or
messages can differ from 2.x:

- `bulk_check()` honours a per-check `context`, and `filter_objects()` passes your context through.
  Context-dependent (ABAC) checks were evaluated against an empty context, so decisions can change.
- `UserInput` accepts `first_name` and `last_name`, which were silently dropped from every check.
- A non-200 response from the PDP raises `PermitConnectionError` with the status code and the
  response body, not "cannot connect to the PDP container", so a rejected API key reads as one.
  Code that matches the old message text needs updating.
- `permit.pdp_api.*` calls honour `pdp_timeout`.
- The blocking client works when called inside a running event loop; 2.x raised
  `RuntimeError: This event loop is already running`.
- `users.sync()` no longer removes `key` from the dict you pass, a path that always returned 422.
- On the blocking `permit.sync.Permit`, the flat `permit.api` methods (D2) sent their request and
  then raised `ValueError: a coroutine was expected`, so a write such as `assign_role()` took
  effect before the error. In 3.0 they return the result. Remove any `except ValueError` added
  around them.
- With `proxy_facts_via_pdp`, `tenants.bulk_create()` and `tenants.bulk_delete()` go to the PDP's
  `/facts/bulk/tenants`; 2.x sent them to its users endpoint.
- `resource_instances.list(detailed_key=...)` works; 2.x raised `TypeError` on the boolean.
- The `tests` package is no longer installed into your site-packages next to `permit`.

## Staying on 2.x for now

If you can't move to 3.0.0 yet, you can still clear the dependency advisories 3.0.0 fixes, as
long as you run Python 3.10 or later. permit 2.8.3 allows `aiohttp>=3.12.14,<4` and
`httpx>=0.24.1,<1`, and no httpx release in that range blocks anyio 4.14.2 (httpx 0.25.1 and
later don't cap anyio; 0.24.x and 0.25.0 reach it through httpcore, which allows anyio below 5).
Add these to your own requirements, constraints or lock file:

```text
permit==2.8.3
aiohttp>=3.14.3          # CVE-2026-69244 and older aiohttp advisories
anyio>=4.14.2            # CVE-2026-63374
h11>=0.16.0              # CVE-2025-43859
pydantic>=2.4.2          # CVE-2024-3772 (or pydantic>=1.10.13,<2 on pydantic 1)
```

**On Python 3.8 or 3.9 this is not possible.** aiohttp 3.14.3 and anyio 4.14.2, the first fixed
releases, both require Python 3.10. `h11>=0.16.0` and the pydantic floor still
install. Until you move to Python 3.10, the advisories give these workarounds:

- CVE-2026-69244 is in aiohttp's C response parser. Setting `AIOHTTP_NO_EXTENSIONS=1` makes
  aiohttp use its Python parser, which is not affected.
- CVE-2026-63374 is in anyio's TLS host name handling. permit never imports httpx or anyio, so it
  concerns only your own code that connects with anyio; the advisory's workaround is to encode
  host names with the `idna` package before connecting.

Security scanners keep reporting both findings until you upgrade Python. permit 2.8.3 itself
needs Python 3.9, because its aiohttp floor does; on 3.8, pip installs an older 2.x release.

## Migrate with an AI agent

The [`permit-python-3-migration`](skills/permit-python-3-migration/) skill walks an AI agent, such
as Claude Code, through this guide: it checks your Python version and stops before editing
anything if the project still allows or runs on 3.8 or 3.9, scans the project, updates the
dependencies, applies the mechanical edits, brings every judgement call to you, and runs your
tests, type checker and linter.

To install it:

- copy the `skills/permit-python-3-migration` folder from this repository into your project's
  `.claude/skills/` directory (or `~/.claude/skills/` for every project); or
- download `permit-python-3-migration.skill` from the
  [3.0.0 release](https://github.com/permitio/permit-python/releases) and unzip it there. The
  file is a zip archive of the same folder.

Then ask the agent to upgrade permit to 3.0.0, or run `/permit-python-3-migration` in Claude Code.
The skill's scanner is read-only and runs on its own:

```bash
python3 .claude/skills/permit-python-3-migration/scripts/scan.py . --json
```
