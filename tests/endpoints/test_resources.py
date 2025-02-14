import uuid

import pytest
from loguru import logger

from permit import ActionBlockEditable, Permit, ResourceCreate
from permit.exceptions import PermitAlreadyExistsError, PermitApiError

TEST_RESOURCE_DOC_KEY = f"documento-{uuid.uuid4()}"
TEST_RESOURCE_FOLDER_KEY = f"folder-{uuid.uuid4()}"
CREATED_RESOURCES = [TEST_RESOURCE_DOC_KEY, TEST_RESOURCE_FOLDER_KEY]


@pytest.mark.xfail()
async def test_resources(permit: Permit):
    logger.info("initial setup of objects")
    len_original = 0
    # initial number of items
    resources = await permit.api.resources.list()
    len_original = len(resources)

    # create first item
    try:
        test_resource = await permit.api.resources.create(
            ResourceCreate(
                key=TEST_RESOURCE_DOC_KEY,
                name=TEST_RESOURCE_DOC_KEY,
                urn="prn:gdrive:test",
                description="a resource",
                actions={
                    "create": ActionBlockEditable(),
                    "read": ActionBlockEditable(),
                    "update": ActionBlockEditable(),
                    "delete": ActionBlockEditable(),
                },
            )
        )
    except PermitAlreadyExistsError:
        logger.info("Resource already exists...")
        test_resource = await permit.api.resources.get(TEST_RESOURCE_DOC_KEY)

    assert test_resource is not None
    assert test_resource.key == TEST_RESOURCE_DOC_KEY
    assert test_resource.name == TEST_RESOURCE_DOC_KEY
    assert test_resource.description == "a resource"
    assert test_resource.urn == "prn:gdrive:test"
    assert test_resource.actions is not None
    assert len(test_resource.actions) == 4
    assert set(test_resource.actions.keys()) == {"create", "read", "update", "delete"}

    # increased number of items by 1
    resources = await permit.api.resources.list()
    assert len(resources) == len_original
    # can find new item in the new list
    assert len([r for r in resources if r.key == test_resource.key]) == 1

    # get non existing -> 404
    with pytest.raises(PermitApiError) as e:
        await permit.api.resources.get("nosuchresource")
    assert e.value.status_code == 404

    # create existing -> 409
    with pytest.raises(PermitApiError) as e:
        await permit.api.resources.create({"key": TEST_RESOURCE_DOC_KEY, "name": "document2", "actions": {}})
    assert e.value.status_code == 409

    # create empty item
    empty = await permit.api.resources.create(
        {
            "key": TEST_RESOURCE_FOLDER_KEY,
            "name": TEST_RESOURCE_FOLDER_KEY,
            "description": "empty resource",
            "actions": {},
        }
    )

    assert empty is not None
    assert empty.key == TEST_RESOURCE_FOLDER_KEY
    assert empty.name == TEST_RESOURCE_FOLDER_KEY
    assert empty.description == "empty resource"
    assert empty.actions is not None
    assert len(empty.actions) == 0

    resources = await permit.api.resources.list()
    assert len(resources) == len_original + 2

    # update actions
    await permit.api.resources.update(
        TEST_RESOURCE_FOLDER_KEY,
        {"description": "wat", "actions": {"pick": {}}},
    )

    # get
    new_empty = await permit.api.resources.get(TEST_RESOURCE_FOLDER_KEY)

    # new_empty changed
    assert new_empty is not None
    assert new_empty.key == TEST_RESOURCE_FOLDER_KEY
    assert new_empty.name == TEST_RESOURCE_FOLDER_KEY
    assert new_empty.description == "wat"
    assert new_empty.actions is not None
    assert len(new_empty.actions) == 1
    assert new_empty.actions.get("pick") is not None
