# Async client

`permit.Permit` is the client for code that runs on an asyncio event loop: every method that
talks to the PDP or the Permit API is a coroutine function. Its blocking twin is
[`permit.sync.Permit`](sync.md); [Async or blocking client](../clients.md) compares them.

::: permit.Permit

::: permit.api.api_client.PermitApiClient
