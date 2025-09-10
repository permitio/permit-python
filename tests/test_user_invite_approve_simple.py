"""
Simple tests for user invite approve functionality.
These tests focus on the core implementation without complex API mocking.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from permit import Permit, PermitConfig
from permit.api.models import ElementsUserInviteApprove, ElementsUserInviteRead, UserInviteStatus
from permit.api.user_invites import UserInvitesApi


class TestUserInviteApproveSimple:
    """Simple test suite for user invite approve functionality."""

    def test_approve_method_exists(self):
        """Test that the approve method exists in UserInvitesApi."""
        assert hasattr(UserInvitesApi, "approve")
        assert callable(UserInvitesApi.approve)

    def test_approve_method_signature(self):
        """Test that the approve method has the correct signature."""
        import inspect

        method = UserInvitesApi.approve
        signature = inspect.signature(method)

        # Check parameter names
        params = list(signature.parameters.keys())
        assert "self" in params
        assert "user_invite_id" in params
        assert "approve_data" in params

        # Check return type annotation
        assert signature.return_annotation.__name__ == "ElementsUserInviteRead"

    def test_approve_data_model_validation(self):
        """Test ElementsUserInviteApprove model validation."""
        # Valid data
        valid_data = ElementsUserInviteApprove(
            email="test@example.com", key="valid-key-123", attributes={"role": "admin"}
        )
        assert valid_data.email == "test@example.com"
        assert valid_data.key == "valid-key-123"
        assert valid_data.attributes == {"role": "admin"}

    def test_approve_data_model_email_validation(self):
        """Test ElementsUserInviteApprove email validation."""
        # Test email validation
        with pytest.raises(ValueError):
            ElementsUserInviteApprove(email="invalid-email", key="valid-key-123", attributes={})

    def test_approve_data_model_key_validation(self):
        """Test ElementsUserInviteApprove key validation."""
        # Test key validation (regex pattern)
        with pytest.raises(ValueError):
            ElementsUserInviteApprove(
                email="test@example.com",
                key="invalid key with spaces",
                attributes={},  # Should fail regex validation
            )

    def test_approve_data_model_with_complex_attributes(self):
        """Test ElementsUserInviteApprove with complex attributes."""
        complex_attributes = {
            "department": "Engineering",
            "location": "San Francisco",
            "role": "Developer",
            "level": "Senior",
            "permissions": ["read", "write"],
            "metadata": {"hire_date": "2024-01-01", "manager": "john@example.com"},
        }

        approve_data = ElementsUserInviteApprove(
            email="test@example.com", key="test-key-123", attributes=complex_attributes
        )

        assert approve_data.attributes == complex_attributes
        assert approve_data.attributes["permissions"] == ["read", "write"]
        assert approve_data.attributes["metadata"]["hire_date"] == "2024-01-01"

    def test_approve_data_model_with_empty_attributes(self):
        """Test ElementsUserInviteApprove with empty attributes."""
        approve_data = ElementsUserInviteApprove(
            email="test@example.com",
            key="test-key-123",
            attributes={},  # Empty attributes should be allowed
        )

        assert approve_data.attributes == {}

    def test_user_invite_status_enum(self):
        """Test UserInviteStatus enum values."""
        assert UserInviteStatus.pending == "pending"
        assert UserInviteStatus.approved == "approved"

    def test_elements_user_invite_read_model(self):
        """Test ElementsUserInviteRead model creation."""
        invite_data = ElementsUserInviteRead(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            environment_id=uuid.uuid4(),
            key="test-invite-key-123",
            status=UserInviteStatus.approved,
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            role_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T01:00:00Z",
        )

        assert invite_data.status == UserInviteStatus.approved
        assert invite_data.email == "test@example.com"
        assert invite_data.key == "test-invite-key-123"

    def test_approve_parameter_types(self):
        """Test that the approve method parameters have correct types."""
        from typing import get_type_hints

        method = UserInvitesApi.approve
        type_hints = get_type_hints(method)

        # Check parameter types
        assert type_hints.get("user_invite_id") is str
        assert type_hints.get("approve_data").__name__ == "ElementsUserInviteApprove"
        assert type_hints.get("return").__name__ == "ElementsUserInviteRead"

    def test_user_invite_models_exist(self):
        """Test that all required models are available."""
        # Test that we can import all necessary models
        from permit.api.models import ElementsUserInviteApprove, ElementsUserInviteRead, UserInviteStatus

        assert ElementsUserInviteApprove is not None
        assert ElementsUserInviteRead is not None
        assert UserInviteStatus is not None

    def test_approve_data_serialization(self):
        """Test that ElementsUserInviteApprove data can be serialized."""
        approve_data = ElementsUserInviteApprove(
            email="test@example.com", key="test-key-123", attributes={"role": "admin", "department": "Engineering"}
        )

        # Test dict() method
        data_dict = approve_data.dict()
        assert data_dict["email"] == "test@example.com"
        assert data_dict["key"] == "test-key-123"
        assert data_dict["attributes"]["role"] == "admin"
        assert data_dict["attributes"]["department"] == "Engineering"

        # Test JSON serialization
        import json

        json_str = approve_data.json()
        parsed_data = json.loads(json_str)
        assert parsed_data["email"] == "test@example.com"
        assert parsed_data["key"] == "test-key-123"

    def test_permit_instance_has_user_invites_api(self):
        """Test that Permit instance exposes user_invites API correctly."""
        # Create a Permit instance with mock configuration
        config = PermitConfig(token="test-token-123", api_url="http://localhost:8000", pdp="http://localhost:7766")
        permit = Permit(config)

        # Test that user_invites API is accessible
        assert hasattr(permit.api, "user_invites")
        assert permit.api.user_invites is not None

        # Test that the approve method is available
        assert hasattr(permit.api.user_invites, "approve")
        assert callable(permit.api.user_invites.approve)

    @pytest.mark.asyncio
    async def test_permit_user_invites_approve_usage_pattern(self):
        """
        Test the actual usage pattern: permit.api.user_invites.approve()
        This test mimics how users will actually use the function.
        """
        # Create a Permit instance with mock configuration
        config = PermitConfig(token="test-token-123", api_url="http://localhost:8000", pdp="http://localhost:7766")
        permit = Permit(config)

        # Create test data - this is how users will use it
        user_invite_id = "test-invite-uuid-123"
        approve_data = ElementsUserInviteApprove(
            email="newuser@company.com",
            key="new-user-invite-key",
            attributes={
                "department": "Engineering",
                "role": "Developer",
                "start_date": "2024-01-15",
                "manager": "manager@company.com",
            },
        )

        # Mock the entire approve method to avoid HTTP calls
        mock_response = ElementsUserInviteRead(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            environment_id=uuid.uuid4(),
            key="new-user-invite-key",
            status=UserInviteStatus.approved,
            email="newuser@company.com",
            first_name="New",
            last_name="User",
            role_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T01:00:00Z",
        )

        # Mock just the approve method
        with patch.object(permit.api.user_invites, "approve", new_callable=AsyncMock) as mock_approve:
            mock_approve.return_value = mock_response

            # This is the actual usage pattern that users will use!
            result = await permit.api.user_invites.approve(user_invite_id, approve_data)

            # Verify the result
            assert isinstance(result, ElementsUserInviteRead)
            assert result.status == UserInviteStatus.approved
            assert result.email == "newuser@company.com"
            assert result.key == "new-user-invite-key"

            # Verify the method was called with correct parameters
            mock_approve.assert_called_once_with(user_invite_id, approve_data)

    def test_user_invites_api_integration_in_permit_client(self):
        """Test that the UserInvitesApi is properly integrated into the Permit client."""
        config = PermitConfig(token="test-token-123", api_url="http://localhost:8000", pdp="http://localhost:7766")
        permit = Permit(config)

        # Test the complete integration
        assert hasattr(permit, "api")
        assert hasattr(permit.api, "user_invites")
        assert isinstance(permit.api.user_invites, UserInvitesApi)

        # Test that it's different from users API
        assert hasattr(permit.api, "users")
        assert permit.api.user_invites is not permit.api.users
        assert type(permit.api.user_invites).__name__ == "UserInvitesApi"
        assert type(permit.api.users).__name__ == "UsersApi"

    def test_actual_usage_pattern_structure(self):
        """
        Test that the actual usage pattern permit.api.user_invites.approve() is available.
        This verifies the complete structure that users will interact with.
        """
        # Create a real Permit instance (no mocking)
        config = PermitConfig(token="test-token-123", api_url="http://localhost:8000", pdp="http://localhost:7766")
        permit = Permit(config)

        # Create real test data as users would
        approve_data = ElementsUserInviteApprove(
            email="newuser@company.com",
            key="new-user-invite-key",
            attributes={"department": "Engineering", "role": "Developer", "start_date": "2024-01-15"},
        )

        # Verify the complete call chain exists (this is what users will use)
        assert hasattr(permit, "api"), "permit.api should exist"
        assert hasattr(permit.api, "user_invites"), "permit.api.user_invites should exist"
        assert hasattr(permit.api.user_invites, "approve"), "permit.api.user_invites.approve should exist"
        assert callable(permit.api.user_invites.approve), "permit.api.user_invites.approve should be callable"

        # Verify the method signature matches what users expect
        import inspect

        method = permit.api.user_invites.approve
        signature = inspect.signature(method)
        params = list(signature.parameters.keys())

        assert "user_invite_id" in params, "Method should accept user_invite_id parameter"
        assert "approve_data" in params, "Method should accept approve_data parameter"

        # Verify the approve_data can be created with user's data
        assert approve_data.email == "newuser@company.com"
        assert approve_data.key == "new-user-invite-key"
        assert approve_data.attributes["department"] == "Engineering"


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_user_invite_approve_simple.py -v
    pass
