# REST API

`permit.api` calls the Permit REST API, one attribute per API: `permit.api.users`,
`permit.api.roles` and so on. On the async client it is a
[`PermitApiClient`][permit.api.api_client.PermitApiClient]; on the blocking client, a
[`SyncPermitApiClient`][permit.api.sync_api_client.SyncPermitApiClient]. Each page below
documents one API, first as the async client has it, then as the blocking client has it.

The [REST API reference](https://api.permit.io/scalar) documents the endpoints these methods
call, and the [Python SDK docs on docs.permit.io](https://docs.permit.io/sdk/python/quickstart-python/)
show them in use.

| Attribute | Page |
|---|---|
| `permit.api.condition_set_rules` | [Condition set rules](condition-set-rules.md) |
| `permit.api.condition_sets` | [Condition sets](condition-sets.md) |
| `permit.api.environments` | [Environments](environments.md) |
| `permit.api.groups` | [Groups](groups.md) |
| `permit.api.pdps` | [PDPs](pdps.md) |
| `permit.api.projects` | [Projects](projects.md) |
| `permit.api.relationship_tuples` | [Relationship tuples](relationship-tuples.md) |
| `permit.api.action_groups` | [Resource action groups](resource-action-groups.md) |
| `permit.api.resource_actions` | [Resource actions](resource-actions.md) |
| `permit.api.resource_attributes` | [Resource attributes](resource-attributes.md) |
| `permit.api.resource_instances` | [Resource instances](resource-instances.md) |
| `permit.api.resource_relations` | [Resource relations](resource-relations.md) |
| `permit.api.resource_roles` | [Resource roles](resource-roles.md) |
| `permit.api.resources` | [Resources](resources.md) |
| `permit.api.role_assignments` | [Role assignments](role-assignments.md) |
| `permit.api.roles` | [Roles](roles.md) |
| `permit.api.tenants` | [Tenants](tenants.md) |
| `permit.api.user_invites` | [User invites](user-invites.md) |
| `permit.api.users` | [Users](users.md) |
| `permit.api.get_user()` and the other flat methods | [Deprecated methods](deprecated.md) |
