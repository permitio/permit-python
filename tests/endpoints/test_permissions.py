from contextlib import contextmanager
import uuid
import pytest
from loguru import logger
from permit import Permit, PermitApiError, RoleCreate, UserCreate, RoleAssignmentCreate

# Test constants
TEST_USER = UserCreate(
    key=str(uuid.uuid4()),
    email="test@permit.io",
    first_name="Test",
    last_name="User",
    attributes={"department": "Engineering"}
)

TEST_ROLE_ADMIN = RoleCreate(
    key=f"admin-{uuid.uuid4()}",
    name="Admin",
    permissions=["Document:read", "Document:write", "Blog:read", "Blog:write"]
)

TEST_ROLE_VIEWER = RoleCreate(
    key=f"viewer-{uuid.uuid4()}",
    name="Viewer",
    permissions=["Document:read", "Blog:read"]
)

@contextmanager
def suppress_409():
    try:
        yield
    except PermitApiError as e:
        if e.status_code != 409:
            raise e
        
@pytest.mark.xfail()
async def setup_test_data(permit: Permit):
    """Helper to setup test user and roles"""
    logger.info("Setting up test data")
    
    with suppress_409():
        await permit.api.users.create(TEST_USER)
    with suppress_409():
        await permit.api.roles.create(TEST_ROLE_ADMIN)
        await permit.api.roles.create(TEST_ROLE_VIEWER)
    
    # Assign roles
    await permit.api.role_assignments.bulk_assign([
        RoleAssignmentCreate(
            user=TEST_USER.key,
            role=TEST_ROLE_ADMIN.key,
            tenant="default"
        ),
        RoleAssignmentCreate(
            user=TEST_USER.key,
            role=TEST_ROLE_VIEWER.key,
            tenant="default"
        )
    ])

@pytest.mark.xfail()
async def test_permissions(permit: Permit):
    await setup_test_data(permit)
    
    logger.info("Testing get_user_permissions")
    # Test permissions retrieval
    role_permissions = await permit.api.permissions.get_user_permissions(TEST_USER.key)
    assert role_permissions is not None
    assert len(role_permissions) == 2
    
    # Verify roles and permissions
    roles = {role.key for role in role_permissions}
    assert TEST_ROLE_ADMIN.key in roles
    assert TEST_ROLE_VIEWER.key in roles
    
    logger.info("Testing filter_objects")
    # Test object filtering with permissions
    test_documents = [
        {"id": "doc1", "name": "Document 1"},
        {"id": "doc2", "name": "Document 2"}
    ]
    
    # Test read permission (should succeed - both roles have it)
    filtered_read = await permit.api.permissions.filter_objects(
        user=TEST_USER.key,
        objects=test_documents,
        action="read",
        resource_type="Document"
    )
    assert len(filtered_read) == 2
    
    # Test write permission (should succeed - admin role has it)
    filtered_write = await permit.api.permissions.filter_objects(
        user=TEST_USER.key,
        objects=test_documents,
        action="write",
        resource_type="Document"
    )
    assert len(filtered_write) == 2
    
    logger.info("Testing filter_objects with IDs")
    # Test filtering with explicit IDs
    filtered_ids = await permit.api.permissions.filter_objects(
        user=TEST_USER.key,
        objects=test_documents,
        action="read",
        resource_type="Document",
        filter_ids=["doc1"]
    )
    assert len(filtered_ids) == 1
    assert filtered_ids[0]["id"] == "doc1"
    
    logger.info("Testing error cases")
    # Test nonexistent user
    with pytest.raises(PermitApiError) as e:
        await permit.api.permissions.get_user_permissions("nonexistent-user")
    assert e.value.status_code == 404

    # Cleanup
    try:
        await permit.api.users.delete(TEST_USER.key)
    except PermitApiError:
        logger.info("Cleanup - user may be already deleted")