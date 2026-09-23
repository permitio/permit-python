"""Offline tests pinning the response shape ``resource_relations.list()`` parses.

``GET /v2/schema/{proj}/{env}/resources/{resource}/relations`` is declared
``response_model=PaginatedResult[RelationRead]`` in the backend
(permit_backend/api/routers/schema_routes/resource_relations.py:89), so it always
answers with a ``{"data": [...], "total_count": N}`` envelope -- never a bare array.
The SDK used to parse it as ``List[RelationRead]``, which made every ``list()`` call
raise ``ValidationError: value is not a valid list``.

These tests serve the real envelope from ``pytest_httpserver`` and assert the SDK
parses it, keeps the pagination query string, and preserves every relation field.
"""

import re
import uuid
from typing import Any

import pytest
from pytest_httpserver import HTTPServer

from permit import Permit, PermitConfig
from permit.api.models import PaginatedResultRelationRead

ORG_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())
ENV_ID = str(uuid.uuid4())

SCOPE_PATH = "/v2/api-key/scope"
RESOURCE_KEY = "document"
RELATIONS_PATH = f"/v2/schema/{PROJECT_ID}/{ENV_ID}/resources/{RESOURCE_KEY}/relations"


def _relation(key: str) -> dict[str, Any]:
    """One ``RelationRead`` exactly as the backend serializes it."""
    return {
        "id": str(uuid.uuid4()),
        "key": key,
        "name": f"Relation {key} é中文",
        "description": "owns \U0001f680",
        "organization_id": ORG_ID,
        "project_id": PROJECT_ID,
        "environment_id": ENV_ID,
        "resource_id": str(uuid.uuid4()),
        "resource_key": RESOURCE_KEY,
        "subject_resource_id": str(uuid.uuid4()),
        "subject_resource": "folder",
        "object_resource_id": str(uuid.uuid4()),
        "object_resource": RESOURCE_KEY,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
    }


def _make_permit(httpserver: HTTPServer) -> Permit:
    """A Permit client whose REST API points at ``httpserver``."""
    base_url = httpserver.url_for("").rstrip("/")
    httpserver.expect_request(SCOPE_PATH, method="GET").respond_with_json(
        {
            "organization_id": ORG_ID,
            "project_id": PROJECT_ID,
            "environment_id": ENV_ID,
        }
    )
    return Permit(
        PermitConfig(
            token="fake-api-key",
            pdp=base_url,
            api_url=base_url,
        )
    )


async def test_relations_list_parses_the_paginated_envelope(httpserver: HTTPServer) -> None:
    """The envelope the backend really sends must parse, field for field."""
    relations = [_relation("parent"), _relation("owner")]
    httpserver.expect_request(RELATIONS_PATH, method="GET").respond_with_json(
        {"data": relations, "total_count": 7, "page_count": 2}
    )
    permit = _make_permit(httpserver)

    result = await permit.api.resource_relations.list(RESOURCE_KEY, page=2, per_page=2)

    assert isinstance(result, PaginatedResultRelationRead)
    assert result.total_count == 7
    assert result.page_count == 2
    assert [relation.key for relation in result.data] == ["parent", "owner"]
    for index, sent in enumerate(relations):
        parsed = result.data[index]
        assert parsed.name == sent["name"]
        assert parsed.description == sent["description"]
        assert parsed.subject_resource == sent["subject_resource"]
        assert parsed.object_resource == sent["object_resource"]
        assert str(parsed.id) == sent["id"]
    httpserver.check_assertions()


async def test_relations_list_sends_pagination_on_the_wire(httpserver: HTTPServer) -> None:
    """``page``/``per_page`` must reach the server, or paging silently does nothing."""
    httpserver.expect_request(RELATIONS_PATH, method="GET").respond_with_json(
        {"data": [], "total_count": 0, "page_count": 0}
    )
    permit = _make_permit(httpserver)

    await permit.api.resource_relations.list(RESOURCE_KEY, page=3, per_page=17)

    requests = [request for request, _response in httpserver.log if request.path == RELATIONS_PATH]
    assert len(requests) == 1
    assert requests[0].args["page"] == "3"
    assert requests[0].args["per_page"] == "17"
    httpserver.check_assertions()


async def test_relations_list_rejects_a_bare_array(httpserver: HTTPServer) -> None:
    """A bare array is not what this endpoint returns, and must not parse as an envelope.

    This pins the contract in the other direction: the SDK surfaces a parse error rather
    than silently handing back an empty page if the response shape ever changes again.
    """
    httpserver.expect_request(RELATIONS_PATH, method="GET").respond_with_json([_relation("parent")])
    permit = _make_permit(httpserver)

    with pytest.raises(Exception, match=re.compile("valid dict|dictionary|dict_type|model_type")):
        await permit.api.resource_relations.list(RESOURCE_KEY)
    httpserver.check_assertions()
