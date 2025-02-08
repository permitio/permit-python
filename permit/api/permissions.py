from typing import List, Dict, Optional
from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import BaseModel, validate_arguments
else:
    from pydantic.v1 import BaseModel, validate_arguments

from .base import (
    BasePermitApi,
    SimpleHttpClient,
)
from .context import ApiContextLevel, ApiKeyAccessLevel

class RolePermission(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        
    name: str
    description: Optional[str] = None
    permissions: List[str]
    attributes: Optional[Dict] = None
    extends: List[str] = []
    granted_to: Optional[str] = None
    key: str
    id: str
    organization_id: str
    project_id: str
    environment_id: str
    created_at: str
    updated_at: str

class PermissionsApi(BasePermitApi):
    @property
    def __users(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/users", use_pdp=True)
        else:
            return self._build_http_client(
                f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/users"
            )

    @property
    def __roles(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/schema/{self.config.api_context.project}/{self.config.api_context.environment}/roles"
        )

    @validate_arguments  # type: ignore[operator]
    async def get_user_permissions(
        self, 
        user: str, 
        resource_type: Optional[str] = None
    ) -> List[RolePermission]:
        """
        Get all permissions for a user.

        Args:
            user: The user key/id
            resource_type: Optional resource type to filter by

        Returns:
            List of role permissions for the user.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        
        user_data = await self.__users.get(f"/{user}", model=Dict)
        permissions = []
        
        for role in user_data.get("roles", []):
            role_data = await self.__roles.get(f"/{role['role']}", model=RolePermission)
            permissions.append(role_data)
        
        return permissions

    @validate_arguments  # type: ignore[operator]
    async def filter_objects(
        self,
        user: str,
        objects: List[Dict],
        action: str,
        resource_type: str,
        id_field: str = "id",
        filter_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Filter objects based on user permissions or provided IDs.

        Args:
            user: The user key/id
            objects: List of objects to filter
            action: The action to check (e.g., "read")
            resource_type: Type of resource
            id_field: Field containing object ID (default: "id")
            filter_ids: Optional list of IDs to filter with

        Returns:
            Filtered list of objects user has permission to access.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)

        if filter_ids is not None:
            return [obj for obj in objects if obj.get(id_field) in filter_ids]
        
        role_permissions = await self.get_user_permissions(user)
        permission_to_check = f"{resource_type}:{action}"
        
        for role in role_permissions:
            if permission_to_check in role.permissions:
                return objects
        return []