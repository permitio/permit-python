import pytest
from loguru import logger
from tests.utils import handle_api_error

from permit.exceptions import PermitApiError, PermitConnectionError
from permit.sync import Permit as SyncPermit

TEST_RESOURCE_DOC_KEY = "documento"
TEST_RESOURCE_FOLDER_KEY = "foldero"
CREATED_RESOURCES = [TEST_RESOURCE_DOC_KEY, TEST_RESOURCE_FOLDER_KEY]


def test_resources_sync(sync_permit: SyncPermit):
    permit = sync_permit
    logger.info("initial setup of objects")
    len_original = 0
    try:
        # initial number of items
        resources = permit.api.resources.list()
        len_original = len(resources)

        # create first item
        test_resource = permit.api.resources.create(
            {
                "key": TEST_RESOURCE_DOC_KEY,
                "name": TEST_RESOURCE_DOC_KEY,
                "urn": "prn:gdrive:test",
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
        assert test_resource.urn == "prn:gdrive:test"
        assert test_resource.actions is not None
        assert len(test_resource.actions) == 4
        assert set(test_resource.actions.keys()) == {"create", "read", "update", "delete"}

        # increased number of items by 1
        resources = permit.api.resources.list()
        assert len(resources) == len_original + 1
        # can find new item in the new list
        assert len([r for r in resources if r.key == test_resource.key]) == 1

        # get non existing -> 404
        with pytest.raises(PermitApiError) as e:
            permit.api.resources.get("nosuchresource")
        assert e.value.status_code == 404

        # create existing -> 409
        with pytest.raises(PermitApiError) as e:
            permit.api.resources.create({"key": TEST_RESOURCE_DOC_KEY, "name": "document2", "actions": {}})
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

        resources = permit.api.resources.list()
        assert len(resources) == len_original + 2

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

    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        # cleanup
        try:
            for resource_key in CREATED_RESOURCES:
                permit.api.resources.delete(resource_key)
            assert len(permit.api.resources.list()) == len_original
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError:
            raise
        except Exception as error:  # noqa: BLE001
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")
