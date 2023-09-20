from typing import List

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments  # type: ignore

from .base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
    required_context,
    required_permissions,
)
from .context import ApiContextLevel, ApiKeyAccessLevel
from .models import (
    AddRolePermissions,
    DerivedRoleRuleCreate,
    DerivedRoleRuleDelete,
    DerivedRoleRuleRead,
    PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings,
    RemoveRolePermissions,
    ResourceRoleCreate,
    ResourceRoleRead,
    ResourceRoleUpdate,
)


class ResourceRolesApi(BasePermitApi):
    """
    Represents the interface for managing resource roles.
    """

    @property
    def __resource_roles(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/schema/{proj_id}/{env_id}/resources".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def list(
        self, resource_key: str, page: int = 1, per_page: int = 100
    ) -> List[ResourceRoleRead]:
        """
        Retrieves a list of resource roles.

        Args:
            resource_key: The key of the resource to filter on.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            A list of resource roles.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.get(
            f"/{resource_key}/roles",
            model=List[ResourceRoleRead],
            params=pagination_params(page, per_page),
        )

    async def _get(self, resource_key: str, role_key: str) -> ResourceRoleRead:
        return await self.__resource_roles.get(
            f"/{resource_key}/roles/{role_key}", model=ResourceRoleRead
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def get(self, resource_key: str, role_key: str) -> ResourceRoleRead:
        """
        Retrieves a resource role by its key.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self._get(resource_key, role_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def get_by_key(self, resource_key: str, role_key: str) -> ResourceRoleRead:
        """
        Retrieves a resource role by its key.
        Alias for the get method.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self._get(resource_key, role_key)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def get_by_id(self, resource_id: str, role_id: str) -> ResourceRoleRead:
        """
        Retrieves a resource role by its ID.
        Alias for the get method.

        Args:
            resource_id: The ID of the resource the role belongs to.
            role_id: The ID of the role.

        Returns:
            The role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self._get(resource_id, role_id)

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def create(
        self, resource_key: str, role_data: ResourceRoleCreate
    ) -> ResourceRoleRead:
        """
        Creates a new resource role.

        Args:
            resource_key: The key of the resource under which the role should be created.
            role_data: The data for the new role.

        Returns:
            The created role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.post(
            f"/{resource_key}/roles", model=ResourceRoleRead, json=role_data
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def update(
        self, resource_key: str, role_key: str, role_data: ResourceRoleUpdate
    ) -> ResourceRoleRead:
        """
        Updates a resource role.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.
            role_data: The updated data for the role.

        Returns:
            The updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.patch(
            f"/{resource_key}/roles/{role_key}", model=ResourceRoleRead, json=role_data
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def delete(self, resource_key: str, role_key: str) -> None:
        """
        Deletes a resource role.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.delete(f"/{resource_key}/roles/{role_key}")

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def assign_permissions(
        self, resource_key: str, role_key: str, permissions: List[str]
    ) -> ResourceRoleRead:
        """
        Assigns permissions to a resource role.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.
            permissions: An array of permission keys (<resourceKey:actionKey>) to be assigned to the role.

        Returns:
            A ResourceRoleRead object representing the updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.post(
            f"/{resource_key}/roles/{role_key}/permissions",
            model=ResourceRoleRead,
            json=AddRolePermissions(permissions=permissions),
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def remove_permissions(
        self, resource_key: str, role_key: str, permissions: List[str]
    ) -> ResourceRoleRead:
        """
        Removes permissions from a resource role.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.
            permissions: An array of permission keys (<resourceKey:actionKey>) to be removed from the role.

        Returns:
            A ResourceRoleRead object representing the updated role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.delete(
            f"/{resource_key}/roles/{role_key}/permissions",
            model=ResourceRoleRead,
            json=RemoveRolePermissions(permissions=permissions),
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def create_role_derivation(
        self, resource_key: str, role_key: str, derivation_rule: DerivedRoleRuleCreate
    ) -> DerivedRoleRuleRead:
        """
        Create a conditional derivation from another role.

        The derivation states that users with some other role on a related object will implicitly also be granted this role.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.
            derivation_rule: A rule when to derived this role from another related role.

        Returns:
            A DerivedRoleRuleRead object representing the newly created role derivation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.post(
            f"/{resource_key}/roles/{role_key}/implicit_grants",
            model=DerivedRoleRuleRead,
            json=derivation_rule,
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def delete_role_derivation(
        self, resource_key: str, role_key: str, derivation_rule: DerivedRoleRuleDelete
    ) -> None:
        """
        Delete a role derivation.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.
            derivation_rule: The details of the derivation rule to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.delete(
            f"/{resource_key}/roles/{role_key}/implicit_grants",
            json=derivation_rule,
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def update_role_derivation_conditions(
        self,
        resource_key: str,
        role_key: str,
        conditions: PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings,
    ) -> PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings:
        """
        Update the optional (ABAC) conditions when to derive this role from other roles.

        Args:
            resource_key: The key of the resource the role belongs to.
            role_key: The key of the role.
            conditions: The conditions object.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__resource_roles.put(
            f"/{resource_key}/roles/{role_key}/implicit_grants/conditions",
            model=PermitBackendSchemasSchemaDerivedRoleDerivedRoleSettings,
            json=conditions,
        )
