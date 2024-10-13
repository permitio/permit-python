from typing import List, Optional

from ..utils.pydantic_version import PYDANTIC_VERSION

if PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from .base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
)
from .context import ApiContextLevel, ApiKeyAccessLevel
from .models import ConditionSetRuleCreate, ConditionSetRuleRead, ConditionSetRuleRemove


class ConditionSetRulesApi(BasePermitApi):
    @property
    def __condition_set_rules(self) -> SimpleHttpClient:
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/set_rules"
        )

    @validate_arguments  # type: ignore[operator]
    async def list(
        self,
        user_set_key: Optional[str] = None,
        permission_key: Optional[str] = None,
        resource_set_key: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> List[ConditionSetRuleRead]:
        """
        Retrieves a list of condition set rule rules.

        Args:
            user_set_key: the key of the userset, if used only rules matching that userset will be fetched.
            permission_key: the key of the permission, formatted as <resource>:<action>.
                if used, only rules granting that permission will be fetched.
            resource_set_key: the key of the resourceset, if used only rules matching that resourceset will be fetched.
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of condition set rule rules.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = pagination_params(page, per_page)
        if user_set_key is not None:
            params.update(user_set=user_set_key)
        if permission_key is not None:
            params.update(permission=permission_key)
        if resource_set_key is not None:
            params.update(resource_set=resource_set_key)
        return await self.__condition_set_rules.get(
            "",
            model=List[ConditionSetRuleRead],
            params=params,
        )

    @validate_arguments  # type: ignore[operator]
    async def create(self, rule: ConditionSetRuleCreate) -> List[ConditionSetRuleRead]:
        """
        Creates a new condition set rule.

        Args:
            rule: The condition set rule to create.

        Returns:
            the created condition set rule.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__condition_set_rules.post("", model=List[ConditionSetRuleRead], json=rule)

    @validate_arguments  # type: ignore[operator]
    async def delete(self, rule: ConditionSetRuleRemove) -> None:
        """
        Deletes a condition set rule.

        Args:
            rule: The condition set rule to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__condition_set_rules.delete("", json=rule)
