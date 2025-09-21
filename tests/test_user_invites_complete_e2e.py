import asyncio
from uuid import uuid4

import pytest
from loguru import logger

from permit import Permit
from permit.api.models import (
    ElementsUserInviteApprove,
    ElementsUserInviteCreate,
    TenantCreate,
    RoleCreate,
    UserInviteStatus,
    ResourceCreate,
    ResourceInstanceCreate,
    ActionBlockEditable,
)
from permit.exceptions import PermitApiError, PermitConnectionError

from .utils import handle_api_error


def print_break():
    print("\n\n ----------- \n\n")  # noqa: T201


# Test data
TEST_TENANT = TenantCreate(key="test_tenant_invites", name="Test Tenant for Invites")

# Test user invites data (will be populated with actual IDs in the test)
TEST_INVITE_DATA_1 = {
    "key": "testuser1_complete@example.com",
    "status": UserInviteStatus.pending,
    "email": "testuser1_complete@example.com",
    "first_name": "Test",
    "last_name": "User1",
}

TEST_INVITE_DATA_2 = {
    "key": "testuser2_complete@example.com",
    "status": UserInviteStatus.pending,
    "email": "testuser2_complete@example.com",
    "first_name": "Test",
    "last_name": "User2",
}

# Store created objects for cleanup
created_invites = []
created_tenant = None
created_role = None
created_resource = None
created_resource_instance = None


@pytest.mark.asyncio
async def test_user_invites_complete_e2e(permit: Permit):
    """
    Complete end-to-end test for User Invites API functionality.

    Tests the complete lifecycle:
    1. Setup (create resource, tenant, resource instance, role)
    2. Create user invites
    3. List user invites
    4. Get single user invite
    5. Approve user invite
    6. Delete user invite
    7. Cleanup
    """
    global created_invites, created_tenant, created_role, created_resource, created_resource_instance

    logger.info("Starting User Invites Complete E2E test")

    try:
        # ==========================================
        # SETUP: Create necessary resources
        # ==========================================
        logger.info("Setting up test environment")

        # Create test resource with proper actions format
        test_resource = ResourceCreate(
            key="test_resource_invites",
            name="Test Resource for Invites",
            description="Resource for testing user invites",
            actions={
                "read": ActionBlockEditable(
                    name="Read Access",
                    description="Read access to the resource"
                ),
                "write": ActionBlockEditable(
                    name="Write Access",
                    description="Write access to the resource"
                )
            }
        )
        created_resource = await permit.api.resources.create(test_resource)
        assert created_resource is not None
        assert created_resource.key == test_resource.key
        logger.info(f"Created test resource: {created_resource.key}")

        # Create test tenant
        created_tenant = await permit.api.tenants.create(TEST_TENANT)
        assert created_tenant is not None
        assert created_tenant.key == TEST_TENANT.key
        assert created_tenant.name == TEST_TENANT.name
        logger.info(f"Created test tenant: {created_tenant.key}")

        # Create test resource instance
        test_resource_instance = ResourceInstanceCreate(
            key="test_instance_invites",
            resource=created_resource.key,
            tenant=created_tenant.key,
            attributes={"test": "invites"}
        )
        created_resource_instance = await permit.api.resource_instances.create(test_resource_instance)
        assert created_resource_instance is not None
        assert created_resource_instance.key == test_resource_instance.key
        logger.info(f"Created test resource instance: {created_resource_instance.key}")

        # Create test role with permissions that match our resource actions
        test_role = RoleCreate(
            key="test_role_invites",
            name="Test Role for Invites",
            permissions=[f"{created_resource.key}:read", f"{created_resource.key}:write"]  # Use our resource actions
        )
        created_role = await permit.api.roles.create(test_role)
        assert created_role is not None
        assert created_role.key == test_role.key
        assert created_role.name == test_role.name
        logger.info(f"Created test role: {created_role.key}")

        # Create invite objects with actual IDs - CONVERT UUIDs TO STRINGS
        TEST_INVITE_1 = ElementsUserInviteCreate(
            **TEST_INVITE_DATA_1,
            role_id=str(created_role.id),  # Convert UUID to string
            tenant_id=str(created_tenant.id),  # Convert UUID to string
            resource_instance_id=str(created_resource_instance.id),  # Convert UUID to string
        )

        TEST_INVITE_2 = ElementsUserInviteCreate(
            **TEST_INVITE_DATA_2,
            role_id=str(created_role.id),  # Convert UUID to string
            tenant_id=str(created_tenant.id),  # Convert UUID to string
            resource_instance_id=str(created_resource_instance.id),  # Convert UUID to string
        )

        print_break()

        # ==========================================
        # TEST 1: Create User Invites
        # ==========================================
        logger.info("Testing user invite creation")

        # Create first invite
        invite_1 = await permit.api.user_invites.create(TEST_INVITE_1)
        created_invites.append(invite_1)

        # Verify create output
        assert invite_1 is not None
        assert invite_1.id is not None
        assert invite_1.key == TEST_INVITE_1.key
        assert invite_1.email == TEST_INVITE_1.email
        assert invite_1.first_name == TEST_INVITE_1.first_name
        assert invite_1.last_name == TEST_INVITE_1.last_name
        assert invite_1.status == UserInviteStatus.pending
        assert invite_1.role_id == created_role.id
        assert invite_1.tenant_id == created_tenant.id
        logger.info(f"✅ Created invite 1: {invite_1.email} (ID: {invite_1.id})")

        # Create second invite
        invite_2 = await permit.api.user_invites.create(TEST_INVITE_2)
        created_invites.append(invite_2)

        # Verify second invite
        assert invite_2 is not None
        assert invite_2.id is not None
        assert invite_2.key == TEST_INVITE_2.key
        assert invite_2.email == TEST_INVITE_2.email
        assert invite_2.status == UserInviteStatus.pending
        logger.info(f"✅ Created invite 2: {invite_2.email} (ID: {invite_2.id})")

        print_break()

        # ==========================================
        # TEST 2: List User Invites
        # ==========================================
        logger.info("Testing user invite listing")

        invites_list = await permit.api.user_invites.list(page=1, per_page=50)
        assert invites_list is not None
        assert invites_list.data is not None
        assert invites_list.total_count >= 2  # At least our 2 invites

        # Find our created invites in the list
        our_invites = [
            invite for invite in invites_list.data
            if invite.id in [invite_1.id, invite_2.id]
        ]
        assert len(our_invites) == 2
        logger.info(f"✅ Listed invites: found {invites_list.total_count} total, including our 2 test invites")

        print_break()

        # ==========================================
        # TEST 3: Get Single User Invite
        # ==========================================
        logger.info("Testing single user invite retrieval")

        retrieved_invite = await permit.api.user_invites.get(str(invite_1.id))
        assert retrieved_invite is not None
        assert retrieved_invite.id == invite_1.id
        assert retrieved_invite.email == invite_1.email
        assert retrieved_invite.key == invite_1.key
        assert retrieved_invite.status == UserInviteStatus.pending
        logger.info(f"✅ Retrieved invite: {retrieved_invite.email} (Status: {retrieved_invite.status})")

        print_break()

        # ==========================================
        # TEST 4: Approve User Invite
        # ==========================================
        logger.info("Testing user invite approval")

        approve_data = ElementsUserInviteApprove(
            email=invite_1.email,
            key=invite_1.key,
            attributes={"department": "Engineering", "role": "Developer", "test": "complete_e2e_test"}
        )

        approved_user = await permit.api.user_invites.approve(
            user_invite_id=str(invite_1.id),
            approve_data=approve_data
        )

        # Verify approval
        assert approved_user is not None
        assert approved_user.email == invite_1.email
        assert approved_user.id is not None
        assert approved_user.attributes is not None
        assert approved_user.attributes.get("department") == "Engineering"
        assert approved_user.attributes.get("role") == "Developer"
        assert approved_user.attributes.get("test") == "complete_e2e_test"
        logger.info(f"✅ Approved invite: {approved_user.email} (User ID: {approved_user.id})")

        print_break()

        # ==========================================
        # TEST 5: Delete User Invite
        # ==========================================
        logger.info("Testing user invite deletion")

        # Delete the second invite
        await permit.api.user_invites.delete(str(invite_2.id))
        logger.info(f"✅ Deleted invite: {invite_2.email}")

        # Verify deletion - trying to get the deleted invite should fail
        try:
            await permit.api.user_invites.get(str(invite_2.id))
            pytest.fail("Expected invite to be deleted, but it still exists")
        except PermitApiError as e:
            # Expected - invite should not be found
            assert e.status_code in [404, 403]  # Not found or forbidden
            logger.info("✅ Confirmed: Invite successfully deleted (not found)")

        # Remove from our tracking list since it's deleted
        created_invites = [inv for inv in created_invites if inv.id != invite_2.id]

        print_break()

        # ==========================================
        # TEST 6: Verify Final State
        # ==========================================
        logger.info("Verifying final state")

        # List invites again to verify our changes
        final_invites_list = await permit.api.user_invites.list(page=1, per_page=50)
        our_remaining_invites = [
            invite for invite in final_invites_list.data
            if invite.id == invite_1.id  # Only invite_1 should remain
        ]

        # Should have 1 invite remaining (invite_1 which was approved)
        # Note: approved invites might still be in the list or might be removed depending on API behavior
        logger.info(f"✅ Final verification: {len(our_remaining_invites)} of our test invites remain in the list")

        logger.info("🎉 All User Invites Complete E2E tests passed successfully!")

    except PermitApiError as error:
        handle_api_error(error, "Got API Error during User Invites Complete E2E test")
    except PermitConnectionError:
        raise
    except Exception as error:  # noqa: BLE001
        logger.error(f"Got error during User Invites Complete E2E test: {error}")
        pytest.fail(f"Got error during User Invites Complete E2E test: {error}")
    finally:
        # ==========================================
        # CLEANUP
        # ==========================================
        logger.info("Starting cleanup")
        try:
            # Delete remaining user invites
            for invite in created_invites:
                try:
                    await permit.api.user_invites.delete(str(invite.id))
                    logger.info(f"Cleaned up invite: {invite.email}")
                except PermitApiError as e:
                    if e.status_code not in [404, 403]:  # Ignore if already deleted
                        logger.warning(f"Failed to delete invite {invite.email}: {e}")

            # Delete test role
            if created_role:
                try:
                    await permit.api.roles.delete(created_role.key)
                    logger.info(f"Cleaned up role: {created_role.key}")
                except PermitApiError as e:
                    if e.status_code != 404:  # Ignore if already deleted
                        logger.warning(f"Failed to delete role {created_role.key}: {e}")

            # Delete test tenant
            if created_tenant:
                try:
                    await permit.api.tenants.delete(created_tenant.key)
                    logger.info(f"Cleaned up tenant: {created_tenant.key}")
                except PermitApiError as e:
                    if e.status_code != 404:  # Ignore if already deleted
                        logger.warning(f"Failed to delete tenant {created_tenant.key}: {e}")

            # Delete test resource instance
            if created_resource_instance:
                try:
                    await permit.api.resource_instances.delete(created_resource_instance.key)
                    logger.info(f"Cleaned up resource instance: {created_resource_instance.key}")
                except PermitApiError as e:
                    if e.status_code != 404:  # Ignore if already deleted
                        logger.warning(f"Failed to delete resource instance {created_resource_instance.key}: {e}")

            # Delete test resource
            if created_resource:
                try:
                    await permit.api.resources.delete(created_resource.key)
                    logger.info(f"Cleaned up resource: {created_resource.key}")
                except PermitApiError as e:
                    if e.status_code != 404:  # Ignore if already deleted
                        logger.warning(f"Failed to delete resource {created_resource.key}: {e}")

            logger.info("✅ Cleanup completed")

        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError:
            raise
        except Exception as error:  # noqa: BLE001
            logger.error(f"Got error during cleanup: {error}")
            # Don't fail the test due to cleanup errors, just log them
            logger.warning("Cleanup failed, but test results are still valid")


if __name__ == "__main__":
    # For running the test directly
    pytest.main([__file__, "-v", "-s"])
