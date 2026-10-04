# PDP API

`permit.pdp_api` calls the APIs that the PDP serves itself, such as the role assignments it
has synced. Only the container PDP serves them. On the async client it is a
`PermitPdpApiClient`; on the blocking client, a `SyncPDPApi`. For running a container PDP,
see the [PDP overview on docs.permit.io](https://docs.permit.io/concepts/pdp/overview/).

::: permit.pdp_api.pdp_api_client.PermitPdpApiClient

::: permit.pdp_api.role_assignments.RoleAssignmentsApi

::: permit.pdp_api.pdp_api_client.SyncPDPApi

::: permit.pdp_api.pdp_api_client.SyncRoleAssignmentsApi

::: permit.pdp_api.models.RoleAssignment
