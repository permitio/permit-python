from typing import TYPE_CHECKING, Any, Union, cast

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

import builtins

from permit.api.base import BasePermitApi, SimpleHttpClient, pagination_params
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import (
    PaginatedResultUserRead,
    RoleAssignmentCreate,
    RoleAssignmentRead,
    RoleAssignmentRemove,
    UserCreate,
    UserCreateBulkOperation,
    UserCreateBulkOperationResult,
    UserDeleteBulkOperation,
    UserDeleteBulkOperationResult,
    UserRead,
    UserReplaceBulkOperation,
    UserReplaceBulkOperationResult,
    UserUpdate,
)
from permit.utils.model_input import ModelInput, ModelListInput

# sync() sends a dict that is not a valid UserCreate as it is, so the annotation
# validate_arguments reads keeps the bare `dict` it always had: `Dict[str, Any]`
# would copy that dict and coerce its keys. Type checkers get `Dict[str, Any]`,
# since pyright's strict mode reports a bare `dict` parameter as partially unknown.
if TYPE_CHECKING:
    _UserSyncInput = UserCreate | dict[str, Any]
else:
    # validate_arguments reads this annotation, so it stays exactly as it was.
    _UserSyncInput = Union[UserCreate, dict]  # noqa: UP007


class UsersApi(BasePermitApi):
    """Manage users and their role assignments."""

    @property
    def __users(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/users", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/users"
        )

    @property
    def __role_assignments(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/role_assignments", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/role_assignments"
        )

    @property
    def __bulk_operations(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/bulk/users", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/bulk/users"
        )

    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> PaginatedResultUserRead:
        """Retrieves a list of users.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            a paginated list of users.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.get(
            "",
            model=PaginatedResultUserRead,
            params=pagination_params(page, per_page),
        )

    async def _get(self, user_key: str) -> UserRead:
        return await self.__users.get(f"/{user_key}", model=UserRead)

    @validate_arguments
    async def get(self, user_key: str) -> UserRead:
        """Retrieves a user by its key.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user_key: The key of the user.

        Returns:
            the user object.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(user_key)

    @validate_arguments
    async def get_by_key(self, user_key: str) -> UserRead:
        """Retrieves a user by its key.

        Alias for the get method.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user_key: The key of the user.

        Returns:
            the user object.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(user_key)

    @validate_arguments
    async def get_by_id(self, user_id: str) -> UserRead:
        """Retrieves a user by its ID.

        Alias for the get method.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user_id: The ID of the user.

        Returns:
            the user object.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self._get(user_id)

    @validate_arguments
    async def create(self, user_data: ModelInput[UserCreate]) -> UserRead:
        """Creates a new user.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user_data: The data for the new user.

        Returns:
            the created user.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.post("", model=UserRead, json=user_data)

    @validate_arguments
    async def update(self, user_key: str, user_data: ModelInput[UserUpdate]) -> UserRead:
        """Updates a user.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user_key: The key of the user.
            user_data: The updated data for the user.

        Returns:
            the updated user.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.patch(f"/{user_key}", model=UserRead, json=user_data)

    @validate_arguments
    async def sync(self, user: _UserSyncInput) -> UserRead:
        """Synchronizes user data by creating or updating a user.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user: The data of the user to be synchronized.

        Returns:
            the result of the user creation or update operation.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        if isinstance(user, dict):
            user_key = user.get("key")
            if user_key is None:
                msg = "required 'key' in input dictionary"
                raise KeyError(msg)
        else:
            user_key = user.key
        return await self.__users.put(f"/{user_key}", model=UserRead, json=user)

    @validate_arguments
    async def delete(self, user_key: str) -> None:
        """Deletes a user.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user_key: The key of the user to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__users.delete(f"/{user_key}")

    @validate_arguments
    async def bulk_create(self, users: ModelListInput[UserCreate]) -> UserCreateBulkOperationResult:
        """Creates users in bulk.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            users: The users to create

        Returns:
            the bulk creation report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.post(
            "",
            model=UserCreateBulkOperationResult,
            json=UserCreateBulkOperation(operations=users),
        )

    @validate_arguments
    async def bulk_replace(
        self, users: ModelListInput[UserCreate]
    ) -> UserReplaceBulkOperationResult:
        """Replaces users in bulk.

        If the user exists - replaces it.
        Otherwise, creates previously non-existing users.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            users: The users to replace.

        Returns:
            the bulk replace report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.put(
            "",
            model=UserReplaceBulkOperationResult,
            json=UserReplaceBulkOperation(operations=users),
        )

    @validate_arguments
    async def bulk_delete(self, users: builtins.list[str]) -> UserDeleteBulkOperationResult:
        """Deletes users in bulk.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            users: The users identities to delete. Each identity can be either the user key or the
                user id.

        Returns:
            the bulk delete report.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__bulk_operations.delete(
            "",
            model=UserDeleteBulkOperationResult,
            json=UserDeleteBulkOperation(idents=users),
        )

    @validate_arguments
    async def assign_role(self, assignment: ModelInput[RoleAssignmentCreate]) -> RoleAssignmentRead:
        """Assigns a role to a user in the scope of a given tenant.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            assignment: The role assignment details.

        Returns:
            the assigned role.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        # validate_arguments has already turned a dict argument into the model.
        assignment = cast("RoleAssignmentCreate", assignment)
        return await self.__users.post(
            f"/{assignment.user}/roles",
            model=RoleAssignmentRead,
            json=assignment.copy(exclude={"user"}),
        )

    @validate_arguments
    async def unassign_role(self, unassignment: ModelInput[RoleAssignmentRemove]) -> None:
        """Unassigns a role from a user in the scope of a given tenant.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            unassignment: The role unassignment details.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        # validate_arguments has already turned a dict argument into the model.
        unassignment = cast("RoleAssignmentRemove", unassignment)
        return await self.__users.delete(
            f"/{unassignment.user}/roles",
            json=unassignment.copy(exclude={"user"}),
        )

    @validate_arguments
    async def get_assigned_roles(
        self,
        user: str,
        tenant: str | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> builtins.list[RoleAssignmentRead]:
        """Retrieves the roles assigned to a user, in one tenant or across all of them.

        The roles come from the given tenant if the tenant filter is provided, or from
        all tenants if it is not.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            user: The key of the user.
            tenant: The key of the tenant.
            page: The page number to fetch.
            per_page: How many items to fetch per page.

        Returns:
            an array of role assignments for the user.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = pagination_params(page, per_page)
        params.update({"user": user})
        if tenant is not None:
            params.update({"tenant": tenant})
        return await self.__role_assignments.get(
            "",
            model=list[RoleAssignmentRead],
            params=params,
        )
