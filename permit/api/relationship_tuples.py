from typing import List, Optional

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
    RelationshipTupleCreate,
    RelationshipTupleDelete,
    RelationshipTupleRead,
)


class RelationshipTuplesApi(BasePermitApi):
    @property
    def __relationship_tuples(self) -> SimpleHttpClient:
        return self._build_http_client(
            "/v2/facts/{proj_id}/{env_id}/relationship_tuples".format(
                proj_id=self.config.api_context.project,
                env_id=self.config.api_context.environment,
            )
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def list(
        self,
        page: int = 1,
        per_page: int = 100,
    ) -> List[RelationshipTupleRead]:
        """
        Retrieves a list of relationship tuples based on the specified filters.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).

        Returns:
            an array of relationship tuples.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        params = pagination_params(page, per_page)
        return await self.__relationship_tuples.get(
            "",
            model=List[RelationshipTupleRead],
            params=params,
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def create(
        self, tuple_data: RelationshipTupleCreate
    ) -> RelationshipTupleRead:
        """
        Creates a new relationship tuple, that states that a relationship (of type: relation)
        exists between two resource instances: the subject and the object.

        Args:
            tuple_data: The relationship tuple to create.

        Returns:
            the created relationship tuple.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__relationship_tuples.post(
            "", model=RelationshipTupleRead, json=tuple_data
        )

    @required_permissions(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
    @required_context(ApiContextLevel.ENVIRONMENT)
    @validate_arguments
    async def delete(self, tuple_data: RelationshipTupleDelete) -> None:
        """
        Removes a relationship tuple.

        Args:
            tuple_data: The relationship tuple to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint context.
        """
        return await self.__relationship_tuples.delete("", json=tuple_data)
