import pytest
from loguru import logger

from permit.exceptions import PermitApiError
from permit.sync import Permit as SyncPermit
from tests.utils import handle_cleanup_error, unique_key

# The whole e2e suite shares a single Permit environment, so every object this
# module creates is namespaced under one prefix. That keeps the keys collision
# proof and -- just as important -- lets the list assertions below be scoped to
# the objects this test itself created instead of counting the environment.
TEST_PREFIX = unique_key("resources-sync")
TEST_RESOURCE_DOC_KEY = f"{TEST_PREFIX}-document"
TEST_RESOURCE_FOLDER_KEY = f"{TEST_PREFIX}-folder"
# The urn is unique per resource server-side as well, so a fixed urn collides
# across runs and across the async/sync variants of this test. The 409 it
# produces quotes the *key*, which makes the collision look like a key clash.
TEST_RESOURCE_DOC_URN = f"prn:gdrive:{TEST_PREFIX}"


def list_own_resource_keys(permit: SyncPermit) -> list[str]:
    """The keys of resources created by this test, sorted, across all pages.

    The shared environment can easily hold more resources than fit on a single
    page, so paging until a short page comes back is what makes the scoped
    assertions hold no matter how much residue other tests left behind.
    """
    per_page = 100
    page = 1
    keys: list[str] = []
    while True:
        resources = permit.api.resources.list(page=page, per_page=per_page)
        keys.extend(resource.key for resource in resources if resource.key.startswith(TEST_PREFIX))
        if len(resources) < per_page:
            return sorted(keys)
        page += 1


def test_resources_sync(sync_permit: SyncPermit) -> None:
    permit = sync_permit
    logger.info("initial setup of objects")
    # none of this test's resources exist yet
    assert list_own_resource_keys(permit) == []

    try:
        # create first item
        test_resource = permit.api.resources.create(
            {
                "key": TEST_RESOURCE_DOC_KEY,
                "name": TEST_RESOURCE_DOC_KEY,
                "urn": TEST_RESOURCE_DOC_URN,
                "description": "a resource",
                "actions": {
                    "create": {},
                    "read": {},
                    "update": {},
                    "delete": {},
                },
            }
        )

        assert test_resource is not None
        assert test_resource.key == TEST_RESOURCE_DOC_KEY
        assert test_resource.name == TEST_RESOURCE_DOC_KEY
        assert test_resource.description == "a resource"
        assert test_resource.urn == TEST_RESOURCE_DOC_URN
        assert test_resource.actions is not None
        assert len(test_resource.actions) == 4
        assert set(test_resource.actions.keys()) == {"create", "read", "update", "delete"}

        # the new item, and only it, shows up in the list
        assert list_own_resource_keys(permit) == [TEST_RESOURCE_DOC_KEY]

        # get non existing -> 404
        with pytest.raises(PermitApiError) as e:
            permit.api.resources.get(unique_key("nosuchresource"))
        assert e.value.status_code == 404

        # create existing -> 409
        with pytest.raises(PermitApiError) as e:
            permit.api.resources.create(
                {"key": TEST_RESOURCE_DOC_KEY, "name": "document2", "actions": {}}
            )
        assert e.value.status_code == 409

        # create empty item
        empty = permit.api.resources.create(
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

        # both of this test's resources are now listed, and nothing else of its own
        assert list_own_resource_keys(permit) == sorted(
            [TEST_RESOURCE_DOC_KEY, TEST_RESOURCE_FOLDER_KEY],
        )

        # update actions
        permit.api.resources.update(
            TEST_RESOURCE_FOLDER_KEY,
            {"description": "wat", "actions": {"pick": {}}},
        )

        # get
        new_empty = permit.api.resources.get_by_key(TEST_RESOURCE_FOLDER_KEY)

        # new_empty changed
        assert new_empty is not None
        assert new_empty.key == TEST_RESOURCE_FOLDER_KEY
        assert new_empty.name == TEST_RESOURCE_FOLDER_KEY
        assert new_empty.description == "wat"
        assert new_empty.actions is not None
        assert len(new_empty.actions) == 1
        assert new_empty.actions.get("pick") is not None
    finally:
        for key in (TEST_RESOURCE_FOLDER_KEY, TEST_RESOURCE_DOC_KEY):
            try:
                permit.api.resources.delete(key)
            except PermitApiError as error:
                handle_cleanup_error(error, f"could not delete resource {key}")
