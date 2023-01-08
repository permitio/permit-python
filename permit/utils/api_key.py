from __future__ import annotations

from permit.config import ApiKeyLevel
from permit.openapi.models.api_key_scope_read import APIKeyScopeRead


def get_api_key_level(scope: APIKeyScopeRead):
    if scope.environment_id is not None:
        return ApiKeyLevel.ENVIRONMENT_LEVEL_API_KEY
    if scope.project_id is not None:
        return ApiKeyLevel.PROJECT_LEVEL_API_KEY
    return ApiKeyLevel.ORGANIZATION_LEVEL_API_KEY
