# Async or blocking client

permit has two clients with the same methods. They differ in how you call them.

| | Async client | Blocking client |
|---|---|---|
| Import | `from permit import Permit` | `from permit.sync import Permit` |
| A call | `await permit.check(...)` | `permit.check(...)` |
| Closing | `async with Permit(...) as permit:` or `await permit.close()` | `with Permit(...) as permit:` or `permit.close()` |
| Reference | [`permit.Permit`](reference/permit.md) | [`permit.sync.Permit`](reference/sync.md) |

## Which to choose

- **Your code is async** (FastAPI, aiohttp, Starlette, or anything else that runs on an
  asyncio event loop): use the async client. Its calls do not block the loop while they wait
  for the Permit API or the PDP.
- **Your code is not async** (Django or Flask views, scripts, worker processes): use the
  blocking client. It runs its calls on an event loop in a background thread of its own and
  waits for them, so your code calls it like any other function. Threads can share one
  client, and its connections.

Calling the blocking client from code that runs on an event loop works, but it blocks that
loop until the call returns, as any blocking call does. In async code, use the async client.

## In this reference

Every page under [`permit.api`](reference/api/index.md), and the
[PDP API](reference/pdp-api.md) and [Elements](reference/elements.md) pages, documents an
API twice: first the class the async client uses, whose methods carry the `async` label,
then its blocking twin, whose name starts with `Sync` and whose methods return their
results. The blocking classes are documented from the stub that type checkers read for
them, so their signatures are the ones your type checker checks your calls against.

[Connections](index.md#connections), on the home page, says how each client opens, shares
and closes its HTTP connections. For how to use the SDK, start with the
[Python quickstart on docs.permit.io](https://docs.permit.io/sdk/python/quickstart-python/).
