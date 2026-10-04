# Models

The models that the SDK's methods take and return, from `permit.api.models`, with their
fields. The package exports each one at the top level too: `from permit import UserCreate`.
A method that takes a model also takes a dict with its fields; see
[Reading the signatures](index.md#reading-the-signatures).

The rest of `permit.api.models`, about 240 more models and enums generated from the Permit
REST API's OpenAPI document, are the types of these models' fields or belong to endpoints the
SDK has no method for. The [REST API reference](https://api.permit.io/scalar) documents every
one of them, with each field's constraints.

::: permit.api.models
    options:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
      separate_signature: false
      show_bases: false
      show_labels: false
      members:
        - APIKeyRead
        - BulkRoleAssignmentReport
        - BulkRoleUnAssignmentReport
        - ConditionSetCreate
        - ConditionSetRead
        - ConditionSetRuleCreate
        - ConditionSetRuleRead
        - ConditionSetRuleRemove
        - ConditionSetUpdate
        - DerivedRoleRuleCreate
        - DerivedRoleRuleDelete
        - DerivedRoleRuleRead
        - ElementsUserInviteApprove
        - ElementsUserInviteCreate
        - ElementsUserInviteRead
        - EnvironmentCopy
        - EnvironmentCreate
        - EnvironmentRead
        - EnvironmentStats
        - EnvironmentUpdate
        - ErrorDetails
        - GroupAddRole
        - GroupAssignment
        - GroupCreate
        - GroupRead
        - GroupReadSchema
        - HTTPValidationError
        - PaginatedResultElementsUserInviteRead
        - PaginatedResultGroupReadSchema
        - PaginatedResultRelationRead
        - PaginatedResultRelationshipTupleDetailedRead
        - PaginatedResultResourceInstanceDetailedRead
        - PaginatedResultRoleAssignmentDetailedRead
        - PaginatedResultUserRead
        - PDPDataRefreshResponse
        - PermitBackendSchemasSchemaDerivedRoleRuleDerivationSettings
        - ProjectCreate
        - ProjectRead
        - ProjectUpdate
        - RelationCreate
        - RelationRead
        - RelationshipTupleCreate
        - RelationshipTupleCreateBulkOperationResult
        - RelationshipTupleDelete
        - RelationshipTupleDeleteBulkOperationResult
        - RelationshipTupleRead
        - ResourceActionCreate
        - ResourceActionGroupCreate
        - ResourceActionGroupRead
        - ResourceActionGroupUpdate
        - ResourceActionRead
        - ResourceActionUpdate
        - ResourceAttributeCreate
        - ResourceAttributeRead
        - ResourceAttributeUpdate
        - ResourceCreate
        - ResourceInstanceCreate
        - ResourceInstanceCreateBulkOperationResult
        - ResourceInstanceDeleteBulkOperationResult
        - ResourceInstanceRead
        - ResourceInstanceUpdate
        - ResourceRead
        - ResourceReplace
        - ResourceRoleCreate
        - ResourceRoleRead
        - ResourceRoleUpdate
        - ResourceUpdate
        - RoleAssignmentCreate
        - RoleAssignmentRead
        - RoleAssignmentRemove
        - RoleCreate
        - RoleRead
        - RoleUpdate
        - TenantCreate
        - TenantCreateBulkOperationResult
        - TenantDeleteBulkOperationResult
        - TenantRead
        - TenantUpdate
        - UserCreate
        - UserCreateBulkOperationResult
        - UserDeleteBulkOperationResult
        - UserRead
        - UserReplaceBulkOperationResult
        - UserUpdate
