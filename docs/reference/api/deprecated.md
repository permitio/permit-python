# Deprecated methods

The flat methods on `permit.api`, such as `permit.api.get_user()`, predate the per-resource
APIs. They still work in 3.x and issue a `DeprecationWarning`; permit 4.0 removes them. Each
one's docstring names the method to use instead. `PermitApiClient` and `SyncPermitApiClient`
get them from the classes below.

::: permit.api.deprecated.DeprecatedApi

::: permit.api.sync_api_client.SyncDeprecatedApi
