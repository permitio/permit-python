"""Offline tests: the SDK parses the responses the published API schema allows.

The schema documents a relationship tuple's ``object_id`` as optional (``null`` means
every resource of the object's type) and its ``*_details`` blocks as optional, and lists
``nats_pdp_config`` as an API key owner type. The models used to require the first two
and lack the third, so a response carrying any of them raised ``ValidationError``.
A user's attribute values must also come back with the JSON types the API sent.

Each test serves a response from ``pytest_httpserver`` through the SDK method that
parses it, or parses the model directly where no SDK method returns it. No API key,
PDP or network is involved.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID, uuid4

import pytest
from pytest_httpserver import HTTPServer

from permit.api.environments import EnvironmentsApi
from permit.api.models import APIKeyOwnerType, RelationshipTupleDetailedRead
from permit.api.relationship_tuples import RelationshipTuplesApi
from permit.api.users import UsersApi
from permit.config import PermitConfig
from tests.utils import FACTS

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc).isoformat()


def ids(*names: str) -> Dict[str, str]:
    return {name: str(uuid4()) for name in names}


def tuple_payload(**fields: Any) -> Dict[str, Any]:
    """A relationship tuple read with every field the schema requires, plus ``fields``."""
    return {
        "subject": "folder:f-1",
        "relation": "parent",
        "object": "document:*",
        "tenant": "tenant-1",
        **ids("id", "subject_id", "relation_id", "tenant_id", "organization_id", "project_id", "environment_id"),
        "created_at": NOW,
        "updated_at": NOW,
        **fields,
    }


# The two ways the schema lets a tuple leave out its object's id.
WILDCARD_OBJECT_ID = [
    pytest.param({"object_id": None}, id="object_id-null"),
    pytest.param({}, id="object_id-absent"),
]


@pytest.mark.parametrize("object_id", WILDCARD_OBJECT_ID)
async def test_relationship_tuples_list_parses_a_tuple_without_an_object_id(
    httpserver: HTTPServer, config: PermitConfig, object_id: Dict[str, Any]
):
    concrete = tuple_payload(object="document:doc-1", object_id=str(uuid4()))
    httpserver.expect_request(f"{FACTS}/relationship_tuples", method="GET").respond_with_json(
        [tuple_payload(**object_id), concrete]
    )

    wildcard, parsed = await RelationshipTuplesApi(config).list()

    assert wildcard.object_id is None
    assert wildcard.object == "document:*"
    assert parsed.object_id == UUID(concrete["object_id"])


@pytest.mark.parametrize("object_id", WILDCARD_OBJECT_ID)
async def test_relationship_tuples_create_parses_a_tuple_without_an_object_id(
    httpserver: HTTPServer, config: PermitConfig, object_id: Dict[str, Any]
):
    httpserver.expect_request(f"{FACTS}/relationship_tuples", method="POST").respond_with_json(
        tuple_payload(**object_id)
    )

    created = await RelationshipTuplesApi(config).create(
        {"subject": "folder:f-1", "relation": "parent", "object": "document:*"}
    )

    assert created.object_id is None


@pytest.mark.parametrize("object_id", WILDCARD_OBJECT_ID)
def test_detailed_relationship_tuple_parses_without_an_object_id_or_details(object_id: Dict[str, Any]):
    # No SDK method returns this model, so it is parsed directly.
    detailed = RelationshipTupleDetailedRead.parse_obj(tuple_payload(**object_id))

    details = (detailed.subject_details, detailed.relation_details, detailed.object_details, detailed.tenant_details)
    assert detailed.object_id is None
    assert details == (None, None, None, None)


def test_detailed_relationship_tuple_still_parses_its_details():
    detailed = RelationshipTupleDetailedRead.parse_obj(
        tuple_payload(
            object="document:doc-1",
            object_id=str(uuid4()),
            subject_details={"key": "f-1", "tenant": "tenant-1", "resource": "folder"},
            relation_details={"key": "parent", "name": "Parent"},
            object_details={"key": "doc-1", "tenant": "tenant-1", "resource": "document"},
            tenant_details={"key": "tenant-1", "name": "Tenant 1"},
        )
    )

    assert detailed.subject_details is not None
    assert detailed.subject_details.resource == "folder"
    assert detailed.relation_details is not None
    assert detailed.relation_details.name == "Parent"
    assert detailed.object_details is not None
    assert detailed.object_details.key == "doc-1"
    assert detailed.tenant_details is not None
    assert detailed.tenant_details.name == "Tenant 1"


async def test_environments_get_api_key_parses_a_nats_pdp_config_key(httpserver: HTTPServer, config: PermitConfig):
    httpserver.expect_request("/v2/api-key/project-1/env-1", method="GET").respond_with_json(
        {
            **ids("id", "organization_id", "project_id", "environment_id"),
            "owner_type": "nats_pdp_config",
            "created_at": NOW,
        }
    )

    key = await EnvironmentsApi(config).get_api_key("project-1", "env-1")

    assert key.owner_type is APIKeyOwnerType.nats_pdp_config


async def test_users_get_keeps_every_attribute_value_and_null_as_sent(httpserver: HTTPServer, config: PermitConfig):
    """Attribute values keep their JSON types: a bool is not an int, a whole float is not an int."""
    attributes = {
        "true": True,
        "false": False,
        "zero": 0,
        "one": 1,
        "negative": -7,
        "half": 0.5,
        "whole_float": 2.0,
        "cleared": None,
        "text": "",
        "nested": {"cleared": None, "mixed": [1, 1.0, True, None, "1"]},
    }
    httpserver.expect_request(f"{FACTS}/users/user-1", method="GET").respond_with_json(
        {
            "key": "user-1",
            **ids("id", "organization_id", "project_id", "environment_id"),
            "created_at": NOW,
            "updated_at": NOW,
            "email": None,
            "first_name": None,
            "attributes": attributes,
        }
    )

    user = await UsersApi(config).get("user-1")

    assert (user.email, user.first_name) == (None, None)
    assert user.attributes == attributes
    # == takes True for 1 and 2.0 for 2. Their JSON text tells them apart.
    assert json.dumps(user.attributes, sort_keys=True) == json.dumps(attributes, sort_keys=True)
