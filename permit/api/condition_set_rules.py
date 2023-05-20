from typing import List, Optional

from permit.config import PermitConfig

from .base import BasePermitApi, ensure_context, pagination_params
from .context import ApiKeyLevel
from .models import ConditionSetRuleCreate, ConditionSetRuleRead, ConditionSetRuleRemove


class ConditionSetRulesApi(BasePermitApi):
    def __init__(self, config: PermitConfig):
        super().__init__(config)
        self.__condition_set_rules = self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/set_rules".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
        return await self.__condition_set_rules.get(
            "",
            model=List[ConditionSetRuleRead],
            params=dict(
                user_set=user_set_key,
                permission=permission_key,
                resource_set=resource_set_key,
                **pagination_params(page, per_page)
            ),
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
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
        return await self.__condition_set_rules.post(
            "", model=List[ConditionSetRuleRead], json=rule.dict()
        )

    @ensure_context(ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY)
    async def delete(self, rule: ConditionSetRuleRemove) -> None:
        """
        Deletes a condition set rule.

        Args:
            rule: The condition set rule to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__condition_set_rules.delete("", json=rule.dict())
