# Blocking client

`permit.sync.Permit` is the client for code that does not run on an event loop. It has the
methods of the async client, [`permit.Permit`](permit.md), and returns their results instead
of coroutines. [Async or blocking client](../clients.md) compares them.

::: permit.sync.Permit
    options:
      inherited_members: true

::: permit.api.sync_api_client.SyncPermitApiClient
