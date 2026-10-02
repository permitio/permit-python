![Python.png](https://raw.githubusercontent.com/permitio/permit-python/main/imgs/Python.png)
# Permit.io Python SDK

Python SDK for interacting with the Permit.io full-stack permissions platform.

## Installation

```py
pip install permit
```

## Documentation

[Read the documentation at Permit.io website](https://docs.permit.io/sdk/python/quickstart-python)

## Upgrading from 2.x

permit 3.0.0 requires Python 3.10 or later and raises the minimum versions of its dependencies.
The [migration guide](https://github.com/permitio/permit-python/blob/main/MIGRATION.md) lists
every breaking change, who it affects and what to change. To have an AI agent such as Claude Code
do the upgrade, use the
[permit-python-3-migration skill](https://github.com/permitio/permit-python/tree/main/skills/permit-python-3-migration).

## Connections

Both clients keep the HTTP connections they open and reuse them for their next requests, so a
request does not pay for a new connection, and a TLS handshake, each time. A client keeps one
pool of connections for the Permit API and one for the PDP, opened by its first request.

### The async client

`permit.Permit` keeps its pools per event loop it is used on, each opened by the first
request from that loop.

```py
async with Permit(token="<YOUR_API_KEY>") as permit:
    allowed = await permit.check("alice", "read", "document")
```

- `await permit.close()` closes the connections, as leaving the `async with` block does.
  Calling it again does nothing more, and the client stays usable: a request sent after it
  opens new connections.
- A client you never close leaves nothing open when its loop shuts down through
  `asyncio.run()`, `asyncio.Runner` or anything else that shuts down the loop's async
  generators before closing it: the client's connections on that loop are closed then. A
  client that is garbage collected while its loop runs closes its connections on that
  loop. As the interpreter exits, the client closes what is still open, so aiohttp reports
  no unclosed session.
- If you drive an event loop yourself, run `await permit.close()` on it before you close it.
  A loop closed with `loop.close()` alone cannot close its connections any more: they stay
  open until the client's next request, from any loop, lets the garbage collector free
  them, and Python reports each one with a `ResourceWarning`. Python's default warning
  filters hide it, but a test suite that turns warnings into errors, such as pytest with
  `filterwarnings = error`, fails on it.
- Close the client once no request is in flight: a request in flight when `close()` runs
  fails.

### The blocking client

`permit.sync.Permit` runs its calls on an event loop in a background daemon thread of its
own, which it starts on its first call. Calls from every thread that uses the client are
handed to that thread and waited for, so they share the client's connections.

```py
from permit.sync import Permit

with Permit(token="<YOUR_API_KEY>") as permit:
    allowed = permit.check("alice", "read", "document")
```

- `permit.close()` waits for the calls other threads have in flight, closes the connections
  and stops the thread, as leaving the `with` block does. A call or a `close()` another
  thread makes meanwhile waits for it to finish. Calling it again does nothing more, and the
  client stays usable: its next call starts a new thread and opens new connections.
- A client you never close is cleaned up when it is garbage collected, or as the
  interpreter exits. The thread never holds up the exit.
- Do not call the blocking client from code that runs on its own background thread, such as
  a callback scheduled on its loop: such a call, and `close()`, raise `RuntimeError` rather
  than wait for themselves.

### Both clients

- With `proxy_facts_via_pdp` on, `wait_for_sync()` yields a client that uses the connections
  of the client it is called on, and on the blocking client its thread too. That client's
  `close()` closes them; the yielded one's `close()` does nothing. With it off, the default,
  `wait_for_sync()` logs a warning and yields the client itself, whose `close()` closes them.
- A child process made by `fork()` leaves the connections it inherits to its parent, and
  opens its own; the blocking client starts a thread of its own in the child.
- The number of connections open at once is not capped, as before. An idle connection is
  closed after aiohttp's keep-alive timeout of 15 seconds.

## Groups

`permit.api.groups` manages groups. A group is a resource instance, of the `group` resource
type unless you name another, whose members inherit the roles granted to the group:

```py
groups = permit.api.groups
await groups.create({"group_instance_key": "engineering", "group_tenant": "default"})
await groups.assign_user("engineering", "alice", tenant="default")
await groups.assign_role(
    "engineering",
    {"role": "editor", "resource": "document", "resource_instance": "readme", "tenant": "default"},
)
# Allowed once the PDP has the change, if the editor role grants "edit" on documents:
await permit.check("alice", "edit", {"type": "document", "key": "readme", "tenant": "default"})
```

- A role granted to a group is a resource role on one resource instance. Members get it
  through ReBAC role derivation over the group instance, so `permit.check()` allows it on
  that instance. It is not a tenant-wide (RBAC) role.
- A method's first argument, `group_instance_key`, takes the group's instance id,
  `"<type>:<key>"` such as `"group:engineering"` or `"team:engineering"`, or the key alone
  (`"engineering"`), which finds only groups of the `group` resource type.
- `assign_group("group:leads", {"group_instance_key": "engineering"})` makes the members of
  `leads` members of `engineering`, so they get the roles granted to `engineering`. The
  members of `engineering` get nothing from `leads`. `remove_group()` undoes it. Both groups
  must be of the same resource type, and the second argument names its group by instance id
  or by key alone, never `"<type>:<key>"`.
- The other methods are `list()`, `get()`, `delete()`, `remove_user()` and `remove_role()`.
  The blocking client, `permit.sync.Permit`, has the same methods.

## Tenant membership

`permit.api.tenants.create_user("acme", {"key": "alice"})` creates the user as a member of the
`acme` tenant, with no role there. Any `role_assignments` in the user data are granted as
`permit.api.users.create()` grants them, each in the tenant it names. It fails with
`PermitAlreadyExistsError` (409) when a user with that key already exists, so give an existing
user a role in the tenant with `permit.api.users.assign_role()` instead. The request always
goes to the Permit REST API, even with `proxy_facts_via_pdp`, and needs an environment-level
API key, or a broader key with the SDK's API context set to the environment.
`permit.api.tenants.delete_tenant_user()` answers 404 for a member with no role, so remove
such a member with `permit.api.users.delete()`.

`permit.get_user_tenants("alice")` asks the PDP for the tenants in which the user has a
tenant-level role, as `TenantDetails` objects with a `key` and `attributes`. Membership
without a role, such as `create_user()` creates, is not listed. Only the container PDP serves
this query: the cloud PDP answers 404, which the SDK raises as a `PermitConnectionError`.
Both methods are on the blocking client too.

## User permissions with context

`permit.get_user_permissions("alice", context={"ip": "10.0.0.1"})` sends the context with the
query, for ABAC policies to read. It is merged over the context store's base context, as
`permit.check()` merges it. A call without `context` sends no context, as in 3.0, so the base
context is not sent either; pass `context={}` to send the base context alone. The blocking
client takes the same argument.

## Detailed lists

`list_detailed()` on `permit.api.role_assignments`, `permit.api.resource_instances` and
`permit.api.relationship_tuples` takes the filters of that API's `list()`, as keyword
arguments, and returns one page of results with the total count:

```py
page = await permit.api.role_assignments.list_detailed(user_key="alice", tenant_key="default")
for assignment in page.data:
    print(assignment.role.name, assignment.tenant.name, assignment.user.email)
```

- A role assignment comes with its role, user and tenant, and the resource instance of a
  resource role, as objects with their names and attributes where `list()` gives their keys.
- A resource instance comes with `relationships`, the relationship tuples whose subject or
  object it is. Its `search_key` matches an instance key or id exactly, where `list()` also
  matches part of a key.
- A relationship tuple comes with `subject_details`, `relation_details`, `object_details` and
  `tenant_details`, which `list()` leaves empty.

They need the API key `list()` needs: an environment-level key, or a broader key with the
SDK's API context set to the environment. The blocking client has the same methods.

## PDP data refresh

`permit.api.pdps.refresh()` makes every PDP connected to the environment fetch all of its
authorization data from Permit again now, instead of at its next periodic update, for
example after data the PDPs decide on changed in an external data source:

```py
refreshed = await permit.api.pdps.refresh(reason="nightly import")
print(refreshed.update_id, refreshed.pdp_ids)
```

- It returns once Permit has triggered the refresh, not once the PDPs have finished it, so
  a check sent right after it may still be answered from the old data.
- `reason` is optional, at most 512 characters, and shows in the PDPs' logs.
- It needs an environment-level API key with write or admin access, or a broader key with
  the SDK's API context set to the environment. The API rejects a read-only key with 403,
  and answers 404 for an environment with no PDP configuration.

## Read-your-writes through the PDP

With `proxy_facts_via_pdp=True`, the facts methods of `permit.api`, those of its `users`,
`tenants`, `role_assignments`, `resource_instances` and `relationship_tuples` APIs, send their
requests to the PDP, which forwards them to the Permit REST API. Only the container PDP serves
them: the cloud PDP answers 404, which the SDK raises as a `PermitApiError` that names the route
and says it needs the container PDP. A client created with `proxy_facts_via_pdp=True` and the
cloud PDP's address as `pdp` issues a `UserWarning` that says so. On some of these writes, the
PDP also waits until the change is in its own data before it answers, so that a check sent next
sees the change:

```py
permit = Permit(token="<YOUR_API_KEY>", pdp="http://localhost:7766", proxy_facts_via_pdp=True)
with permit.wait_for_sync(timeout=5) as synced:
    await synced.api.users.assign_role({"user": "alice", "role": "editor", "tenant": "default"})
# Allowed, if the editor role grants "edit" on documents:
await permit.check("alice", "edit", {"type": "document", "tenant": "default"})
```

The PDP waits on the writes of these methods only:

- `users.create()`, `users.update()`, `users.sync()`, `users.assign_role()` and
  `users.unassign_role()`;
- `tenants.create()`;
- `role_assignments.assign()` and `role_assignments.unassign()`;
- `resource_instances.create()` and `resource_instances.update()`;
- `relationship_tuples.create()`.

It forwards every other facts request without waiting, reads included. These writes return
before the PDP has the change, so a check sent right after one may still see the old data:

- `users.delete()`, `users.bulk_create()`, `users.bulk_replace()` and `users.bulk_delete()`;
- `tenants.update()`, `tenants.delete()`, `tenants.delete_tenant_user()`,
  `tenants.bulk_create()` and `tenants.bulk_delete()`;
- `role_assignments.bulk_assign()` and `role_assignments.bulk_unassign()`;
- `resource_instances.delete()`, `resource_instances.bulk_replace()` and
  `resource_instances.bulk_delete()`;
- `relationship_tuples.delete()`, `relationship_tuples.bulk_create()` and
  `relationship_tuples.bulk_delete()`.

`tenants.create_user()` always goes to the API, so it does not wait either. A deprecated flat
method on `permit.api`, such as `permit.api.sync_user()`, waits when the method its warning
names does.

- How long the PDP waits is `facts_sync_timeout`, or the `timeout` of `wait_for_sync()` for
  the client it yields, sent as the `X-Wait-Timeout` header. With `0` the time is up at once,
  so the PDP does not wait, and the policy below decides the answer: with `"fail"`, every
  write that waits answers 424. With `None`, the default of `facts_sync_timeout`, the SDK
  sends no header, and the PDP waits its own default: 10 seconds, unless its
  `PDP_LOCAL_FACTS_WAIT_TIMEOUT` sets another.
- `facts_sync_timeout_policy`, or the `policy` of `wait_for_sync()`, says what the PDP does
  when the time is up first: `"ignore"` answers with the write's own response, and `"fail"`
  answers 424, which the SDK raises as a `PermitApiError`. The write is done either way.
- The blocking client, `permit.sync.Permit`, waits on the same methods.

## Type checking

The package ships a `py.typed` marker (PEP 561), so mypy, pyright and IDEs check your
calls into the SDK against its type annotations. No pydantic mypy plugin is needed.

- The SDK's models are pydantic v1 models under both pydantic majors (with pydantic 2
  installed they come from `pydantic.v1`), and type checkers see them that way: use
  `.dict()` and `.json()` on them, not `.model_dump()`.
- Methods that take a model also accept an equivalent dict, such as
  `permit.api.users.create({"key": "user"})`, and bulk methods take a list of either.
  The dict is still validated at runtime.
- Model constructors are typed by their fields, so a nested model field takes a model
  instance, not a dict:
  `ResourceCreate(key="doc", name="Doc", actions={"read": ActionBlockEditable()})`.
  pydantic accepts a nested dict there at runtime, but a type checker rejects it. To
  pass plain dicts, give the whole payload to the API method as a dict instead.
- The blocking client, `permit.sync.Permit`, is typed as blocking:
  `permit.api.users.get("user")` returns a `UserRead`, not a coroutine.

## Logging

The SDK logs with [loguru](https://github.com/Delgan/loguru) and logs nothing unless you
enable it in the `log` option:

```py
permit = Permit(token="<YOUR_API_KEY>", log={"enable": True, "level": "debug"})
```

- The SDK adds no loguru sink of its own. Its records go to the sinks your application has
  added, or to loguru's default stderr sink, in the format of those sinks.
- `"enable": False` (the default) calls loguru's `logger.disable("permit")`. `"enable": True`
  undoes that call, with `logger.enable("permit")`, only if an earlier client made it, so a
  `logger.disable()` your application made for `permit` or one of its modules still
  applies. When it does undo it, loguru also drops any `permit.*` module disable made since.
- `level` (default `"info"`) is the lowest severity the SDK logs. Its records below it never
  reach a sink. Your application's own records are not affected. The SDK logs its HTTP
  requests and the PDP's responses at `"debug"`. With `"enable": True`, for a level name
  loguru does not know, the SDK logs a warning that names it and uses `"info"`.
- `label` (default `"Permit"`) is put in square brackets before every message the SDK logs.
- `json` is not applied. For JSON output, give your application a serialized sink in place
  of loguru's default one: `logger.remove()`, then `logger.add(sys.stderr, serialize=True)`.
  Added next to the default sink, it prints every record a second time.
- loguru's logger is process-wide, so these settings are too: the client created last
  decides whether the SDK logs, and the last one created with `"enable": True` decides the
  level and the label, for every client in the process. `wait_for_sync()` creates no
  client: it yields a copy of the client it is called on.
- The SDK replaces the API key of every client in the process with `[REDACTED]` in the
  messages it logs and in the PDP error bodies it puts in a `PermitConnectionError`, so a
  PDP that echoes the key back does not expose it. A user name and password written into
  the `api_url` or `pdp` URL are not replaced: the SDK logs its request URLs at `"debug"`.

## Deprecations

A future major release, permit 4.0, will remove the following. They still work in 3.x, and
each one issues a `DeprecationWarning` that says what to do instead.

- **pydantic 1 support.** On pydantic 1, `import permit` warns once. Upgrade to pydantic 2.
  The SDK's models then come from `pydantic.v1`, so their methods stay the same, but
  invalid input raises `pydantic.v1.ValidationError` rather than `pydantic.ValidationError`.
  Catching `pydantic.v1.ValidationError` works under both majors. Until you upgrade, the
  warning filter `ignore:Support for pydantic 1:DeprecationWarning` silences the import warning.
- **The flat methods on `permit.api`**, such as `permit.api.get_user()`. Use the grouped
  APIs instead, such as `permit.api.users.get()`. Each flat method's warning names its
  replacement.
- **`permit.api.tenants.add_user()`**, an alias of `permit.api.tenants.create_user()`. The
  route creates the user, so `create_user()` is the name that says what it does.
- **The `detailed_key` argument of `permit.api.resource_instances.list()`**, which sends a
  query parameter the API has deprecated. Use `permit.api.resource_instances.list_detailed()`
  instead (see [Detailed lists](#detailed-lists)). Only a call that passes `detailed_key=True`
  or `detailed_key=False` warns.

By default, Python shows these warnings only when the code that triggers them is in
`__main__`, such as the script you run. pytest shows them in its warnings summary. To see
them elsewhere, such as in a web app, run Python with `-W default::DeprecationWarning` or
set the environment variable `PYTHONWARNINGS=default::DeprecationWarning`.

## Contributing

See [CONTRIBUTING.md](https://github.com/permitio/permit-python/blob/main/CONTRIBUTING.md).
