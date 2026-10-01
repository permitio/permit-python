from typing import TYPE_CHECKING

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from permit.api.base import BasePermitApi, SimpleHttpClient, pagination_params
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import (
    GroupAddRole,
    GroupAssignment,
    GroupAssignUser,
    GroupCreate,
    GroupRead,
    GroupReadSchema,
    PaginatedResultGroupReadSchema,
)
from permit.utils.model_input import ModelInput


class GroupsApi(BasePermitApi):
    """Manage groups, whose members inherit the roles granted to the group.

    A group is an instance of a group resource type (``group`` unless you name another) in
    one tenant. A user added to a group gets the ``member`` role on the group instance. A
    role granted to a group is a resource role on one resource instance, and it reaches the
    group's members through ReBAC: a role derivation grants it to every user who has the
    ``member`` role on the group instance. ``permit.check()`` then allows a member what that
    role allows on that instance. It is not a tenant-wide (RBAC) role: a check must name
    the resource instance, and a check that names only the resource type does not use it.

    Every method needs an environment-level API key, or a project- or organization-level
    key with the SDK's API context set to the environment.

    The ``group_instance_key`` argument of every method but ``list()`` and ``create()``
    accepts any of:

    - the group instance's id, the ``id`` that ``get()`` and ``list()`` return;
    - ``"<type>:<key>"``, the group's resource type key and instance key, such as
      ``"group:engineering"`` or ``"team:engineering"``;
    - the instance key alone, such as ``"engineering"``. The API reads it as
      ``"group:engineering"``, so it finds only groups of the ``group`` resource type. Name
      a group of any other resource type by its id or by the ``"<type>:<key>"`` form.
    """

    @property
    def __groups(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/groups"
        )

    @validate_arguments
    async def list(self, page: int = 1, per_page: int = 100) -> PaginatedResultGroupReadSchema:
        """Lists the environment's groups, of every group resource type.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            page: The page number to fetch, starting at 1 (default: 1).
            per_page: How many groups to fetch per page, at most 100 (default: 100).

        Returns:
            One page of groups, with the total count. Each group's ``group_instance_key`` is
            its instance key alone, and ``id`` is its instance id.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__groups.get(
            "/direct",
            model=PaginatedResultGroupReadSchema,
            params=pagination_params(page, per_page),
        )

    @validate_arguments
    async def get(self, group_instance_key: str) -> GroupReadSchema:
        """Retrieves a group.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group, by instance id, by ``"<type>:<key>"`` such as
                ``"group:engineering"``, or by instance key alone if it is of the ``group``
                resource type.

        Returns:
            The group. Its ``group_instance_key`` is its instance key alone, and ``id`` is
            its instance id.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when no
                such group exists.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__groups.get(f"/direct/{group_instance_key}", model=GroupReadSchema)

    @validate_arguments
    async def create(self, group_data: ModelInput[GroupCreate]) -> GroupRead:
        """Creates a group.

        The group is a new instance of the resource type ``group_data.group_resource_type_key``
        (``group`` if not set) in the tenant ``group_data.group_tenant``. The API creates that
        resource type if it does not exist, and adds to it the ``member`` role that group
        membership uses if it has none.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_data: The group to create. Its ``group_instance_key`` is the new instance's
                key alone, such as ``"engineering"``, not ``"group:engineering"``; its
                ``group_tenant`` is the key or id of the tenant the group belongs to.

        Returns:
            The created group.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 409 when the
                group already exists.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__groups.post("", model=GroupRead, json=group_data)

    @validate_arguments
    async def delete(self, group_instance_key: str) -> None:
        """Deletes a group: the group's resource instance.

        When no instance of the group's resource type remains, the API also deletes that
        resource type's ``member`` role.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group, by instance id, by ``"<type>:<key>"`` such as
                ``"group:engineering"``, or by instance key alone if it is of the ``group``
                resource type.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when no
                such group exists.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        await self.__groups.delete(f"/{group_instance_key}")

    @validate_arguments
    async def assign_user(self, group_instance_key: str, user_key: str, tenant: str) -> GroupRead:
        """Adds a user to a group.

        The user gets the ``member`` role on the group instance, in the group's tenant.
        Through it, the user gets the roles granted to the group with ``assign_role()``, and
        those of each group ``other`` after
        ``assign_group(<this group>, {"group_instance_key": other})``.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group, by instance id, by ``"<type>:<key>"`` such as
                ``"group:engineering"``, or by instance key alone if it is of the ``group``
                resource type.
            user_key: The key or id of the user to add.
            tenant: The key of the group's tenant. The API requires it, and the membership
                always applies in the tenant the group belongs to.

        Returns:
            The group, with the ids of the users added to it and its assigned roles.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when the
                group or the user does not exist.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__groups.put(
            f"/{group_instance_key}/users/{user_key}",
            model=GroupRead,
            json=GroupAssignUser(tenant=tenant),
        )

    @validate_arguments
    async def remove_user(self, group_instance_key: str, user_key: str, tenant: str) -> None:
        """Removes a user from a group.

        The user loses the ``member`` role on the group instance, and with it the roles the
        group passed on, unless the user holds them some other way.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group, by instance id, by ``"<type>:<key>"`` such as
                ``"group:engineering"``, or by instance key alone if it is of the ``group``
                resource type.
            user_key: The key or id of the user to remove.
            tenant: The key of the group's tenant. The API requires it, and the membership
                always applies in the tenant the group belongs to.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when the
                group or the user does not exist.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        await self.__groups.delete(
            f"/{group_instance_key}/users/{user_key}",
            json=GroupAssignUser(tenant=tenant),
        )

    @validate_arguments
    async def assign_role(
        self, group_instance_key: str, role_data: ModelInput[GroupAddRole]
    ) -> GroupRead:
        """Grants a group a resource role on one resource instance.

        Every member of the group gets the role on that instance through ReBAC: the API links
        the group instance to the resource instance and derives the role from the group's
        ``member`` role. Users who join the group later get it too, and members who leave
        lose it. The role applies to that instance only, not tenant-wide.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group, by instance id, by ``"<type>:<key>"`` such as
                ``"group:engineering"``, or by instance key alone if it is of the ``group``
                resource type.
            role_data: What to grant. ``role`` is the key or id of a role of ``resource``.
                ``resource`` is the resource's key and ``resource_instance`` the instance's
                key: the API looks up ``"<resource>:<resource_instance>"`` in the group's
                tenant and creates the instance there if it does not exist. ``tenant`` is
                required by the API: pass the group's tenant.

        Returns:
            The group, with the ids of the users added to it and its assigned roles.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when the
                group, the resource or the role does not exist.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__groups.post(
            f"/{group_instance_key}/roles", model=GroupRead, json=role_data
        )

    @validate_arguments
    async def remove_role(
        self, group_instance_key: str, role_data: ModelInput[GroupAddRole]
    ) -> None:
        """Revokes a resource role on one resource instance from a group.

        The group's members lose the role on that instance, unless they hold it some other
        way.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group, by instance id, by ``"<type>:<key>"`` such as
                ``"group:engineering"``, or by instance key alone if it is of the ``group``
                resource type.
            role_data: What to revoke, as it was granted with ``assign_role()``. ``role`` and
                ``resource`` are keys or ids, ``resource_instance`` is the instance's key or
                id. ``tenant`` is required by the API: pass the group's tenant.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when the
                group, the role or the resource instance does not exist.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        await self.__groups.delete(f"/{group_instance_key}/roles", json=role_data)

    @validate_arguments
    async def assign_group(
        self, group_instance_key: str, assignment: ModelInput[GroupAssignment]
    ) -> GroupRead:
        """Makes the members of one group members of another.

        Every member of the group ``group_instance_key`` gets the ``member`` role on the group
        named in ``assignment``, and through it the roles granted to that group. It works in
        that direction only: the members of the group in ``assignment`` gain nothing from
        ``group_instance_key``. For example, after
        ``assign_group("group:leads", {"group_instance_key": "engineering"})`` the members of
        ``leads`` have the roles granted to ``engineering``. Both groups must be of the same
        group resource type.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group whose members join the other group, by instance
                id, by ``"<type>:<key>"`` such as ``"group:leads"``, or by instance key alone
                if it is of the ``group`` resource type.
            assignment: The group they join. Its ``group_instance_key`` is that group's
                instance id or its instance key alone, such as ``"engineering"``: the
                ``"<type>:<key>"`` form is not accepted here.

        Returns:
            The group ``group_instance_key``.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when
                either group does not exist, or 409 when the members of the first group are
                already members of the second this way.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__groups.put(
            f"/{group_instance_key}/assign_group", model=GroupRead, json=assignment
        )

    @validate_arguments
    async def remove_group(
        self, group_instance_key: str, assignment: ModelInput[GroupAssignment]
    ) -> None:
        """Undoes ``assign_group()``: the members of one group stop being members of another.

        The members of the group ``group_instance_key`` lose the ``member`` role on the group
        named in ``assignment``, and the roles that came with it, unless they hold them some
        other way.

        Needs an environment-level API key, or a broader key with the SDK's API context
        set to the environment.

        Args:
            group_instance_key: The group whose members leave the other group, by instance
                id, by ``"<type>:<key>"`` such as ``"group:leads"``, or by instance key alone
                if it is of the ``group`` resource type.
            assignment: The group they leave. Its ``group_instance_key`` is that group's
                instance id or its instance key alone, such as ``"engineering"``: the
                ``"<type>:<key>"`` form is not accepted here.

        Raises:
            PermitApiError: If the API returns an error HTTP status code, such as 404 when
                either group does not exist.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        await self.__groups.delete(f"/{group_instance_key}/assign_group", json=assignment)
