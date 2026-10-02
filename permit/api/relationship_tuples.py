from typing import TYPE_CHECKING

from permit.utils.pydantic_version import PYDANTIC_VERSION

if TYPE_CHECKING:
    # The v1 API is what runs under either pydantic major, so type-check against it.
    from pydantic.v1 import validate_arguments
elif PYDANTIC_VERSION < (2, 0):
    from pydantic import validate_arguments
else:
    from pydantic.v1 import validate_arguments

from permit.api.base import (
    BasePermitApi,
    SimpleHttpClient,
    pagination_params,
)
from permit.api.context import ApiContextLevel, ApiKeyAccessLevel
from permit.api.models import (
    PaginatedResultRelationshipTupleDetailedRead,
    RelationshipTupleCreate,
    RelationshipTupleCreateBulkOperation,
    RelationshipTupleCreateBulkOperationResult,
    RelationshipTupleDelete,
    RelationshipTupleDeleteBulkOperation,
    RelationshipTupleDeleteBulkOperationResult,
    RelationshipTupleRead,
)
from permit.utils.model_input import ModelInput, ModelListInput


def _filter_params(
    *,
    page: int,
    per_page: int,
    subject_key: str | None,
    relation_key: str | None,
    object_key: str | None,
    tenant_key: str | None,
) -> list[tuple[str, str | int]]:
    """The query of a relationship tuples list: pagination, then the filters given."""
    params = list(pagination_params(page, per_page).items())

    if subject_key is not None:
        params.append(("subject", subject_key))
    if relation_key is not None:
        params.append(("relation", relation_key))
    if object_key is not None:
        params.append(("object", object_key))
    if tenant_key is not None:
        params.append(("tenant", tenant_key))
    return params


class RelationshipTuplesApi(BasePermitApi):
    """Manage relationship tuples between resource instances (ReBAC)."""

    @property
    def __relationship_tuples(self) -> SimpleHttpClient:
        if self.config.proxy_facts_via_pdp:
            return self._build_http_client("/facts/relationship_tuples", use_pdp=True)
        return self._build_http_client(
            f"/v2/facts/{self.config.api_context.project}/{self.config.api_context.environment}/relationship_tuples"
        )

    @validate_arguments
    async def list(  # noqa: PLR0917 - public signature; callers may pass these positionally
        self,
        page: int = 1,
        per_page: int = 100,
        subject_key: str | None = None,
        relation_key: str | None = None,
        object_key: str | None = None,
        tenant_key: str | None = None,
    ) -> list[RelationshipTupleRead]:
        """Retrieves a list of relationship tuples based on the specified filters.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            page: The page number to fetch (default: 1).
            per_page: How many items to fetch per page (default: 100).
            subject_key: if specified, only relationship tuples with this subject will be fetched.
            relation_key: if specified, only relationship tuples with this relation will be fetched.
            object_key: if specified, only relationship tuples with this object will be fetched.
            tenant_key: if specified, only relationship tuples with this tenant will be fetched.

        Returns:
            an array of relationship tuples.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = _filter_params(
            page=page,
            per_page=per_page,
            subject_key=subject_key,
            relation_key=relation_key,
            object_key=object_key,
            tenant_key=tenant_key,
        )

        return await self.__relationship_tuples.get(
            "",
            model=list[RelationshipTupleRead],
            params=params,
        )

    @validate_arguments
    async def list_detailed(
        self,
        *,
        page: int = 1,
        per_page: int = 100,
        subject_key: str | None = None,
        relation_key: str | None = None,
        object_key: str | None = None,
        tenant_key: str | None = None,
    ) -> PaginatedResultRelationshipTupleDetailedRead:
        """Lists relationship tuples with their subject, relation, object and tenant.

        Takes the same filters as ``list()``, as keyword arguments. Each tuple carries what
        ``list()`` returns, and also fills in the fields ``list()`` leaves empty:
        ``subject_details`` and ``object_details`` (each resource instance's key, resource
        type, tenant and attributes), ``relation_details`` (the relation's key, name and
        description) and ``tenant_details`` (the tenant's key, name, description and
        attributes).

        Needs an environment-level API key, or a project- or organization-level key with the
        SDK's API context set to the environment.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            page: The page number to fetch, starting at 1 (default: 1).
            per_page: How many items to fetch per page, at most 100 (default: 100).
            subject_key: if specified, only relationship tuples with this subject will be
                fetched: `resource_type:instance_key` or the resource instance id.
            relation_key: if specified, only relationship tuples with this relation will be
                fetched.
            object_key: if specified, only relationship tuples with this object will be
                fetched: `resource_type:instance_key` or the resource instance id.
            tenant_key: if specified, only relationship tuples in this tenant will be fetched.

        Returns:
            One page of detailed relationship tuples, with the total count across all pages.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        params = _filter_params(
            page=page,
            per_page=per_page,
            subject_key=subject_key,
            relation_key=relation_key,
            object_key=object_key,
            tenant_key=tenant_key,
        )
        return await self.__relationship_tuples.get(
            "/detailed",
            model=PaginatedResultRelationshipTupleDetailedRead,
            params=params,
        )

    @validate_arguments
    async def create(
        self, tuple_data: ModelInput[RelationshipTupleCreate]
    ) -> RelationshipTupleRead:
        """Creates a new relationship tuple.

        The tuple states that a relationship (of type: relation) exists between two
        resource instances: the subject and the object.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            tuple_data: The relationship tuple to create.

        Returns:
            the created relationship tuple.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__relationship_tuples.post(
            "", model=RelationshipTupleRead, json=tuple_data
        )

    @validate_arguments
    async def delete(self, tuple_data: ModelInput[RelationshipTupleDelete]) -> None:
        """Removes a relationship tuple.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            tuple_data: The relationship tuple to delete.

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__relationship_tuples.delete("", json=tuple_data)

    @validate_arguments
    async def bulk_create(
        self, tuples: ModelListInput[RelationshipTupleCreate]
    ) -> RelationshipTupleCreateBulkOperationResult:
        """Creates multiple relationship tuples at once using the provided tuple data.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            tuples: The relationship tuples to create.
                Each tuple object is of type RelationshipTupleCreate and is essentially
                a tuple of (subject, relation, object, tenant).

                subject and object are both resource instances, formatted as
                `<resourcetype:instancekey>` strings (e.g: Folder:budget23).
                relation is the name of the relation.
                tenant is the key of the tenant in which to place the relation
                (optional if at least one of subject/object already exists).

                Subject and object must both be resource instances *in the same tenant*!

        Returns:
            the tuples creation result (RelationshipTupleCreateBulkOperationResult)

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__relationship_tuples.post(
            "/bulk",
            model=RelationshipTupleCreateBulkOperationResult,
            json=RelationshipTupleCreateBulkOperation(operations=tuples),
        )

    @validate_arguments
    async def bulk_delete(
        self, tuples: ModelListInput[RelationshipTupleDelete]
    ) -> RelationshipTupleDeleteBulkOperationResult:
        """Deletes multiple relationship tuples at once using the provided tuple data.

        Container PDP only with ``proxy_facts_via_pdp`` on: the request then goes to the
        PDP's ``/facts`` routes, which the cloud PDP does not serve. It answers 404, which
        this method raises as a ``PermitApiError`` that says so.

        Args:
            tuples: The relationship tuples to delete.
                Each tuple object is of type RelationshipTupleDelete and is essentially
                a tuple of (subject, relation, object).

                subject and object are both resource instances, formatted as
                `<resourcetype:instancekey>` strings (e.g: Folder:budget23).
                relation is the name of the relation.

        Returns:
            the tuples deletion result (RelationshipTupleDeleteBulkOperationResult)

        Raises:
            PermitApiError: If the API returns an error HTTP status code.
            PermitContextError: If the configured ApiContext does not match the required endpoint
                context.
        """
        await self._ensure_access_level(ApiKeyAccessLevel.ENVIRONMENT_LEVEL_API_KEY)
        await self._ensure_context(ApiContextLevel.ENVIRONMENT)
        return await self.__relationship_tuples.delete(
            "/bulk",
            model=RelationshipTupleDeleteBulkOperationResult,
            json=RelationshipTupleDeleteBulkOperation(idents=tuples),
        )
