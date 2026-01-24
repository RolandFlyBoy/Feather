"""Unit tests for exception classes and error response builders.

Tests exception attributes, inheritance, and the standardized
error/success response format.
"""

import pytest
from datetime import datetime

pytestmark = pytest.mark.unit


class TestExceptionAttributes:
    """Test that exceptions have required attributes."""

    def test_feather_exception_has_message(self):
        """FeatherException has message attribute."""
        from feather import FeatherException
        exc = FeatherException("Test error")
        assert exc.message == "Test error"

    def test_feather_exception_has_status_code(self):
        """FeatherException has status_code attribute."""
        from feather import FeatherException
        exc = FeatherException("Test error", status_code=400)
        assert exc.status_code == 400

    def test_feather_exception_has_error_code(self):
        """FeatherException has error_code attribute."""
        from feather import FeatherException
        exc = FeatherException("Test error", error_code="CUSTOM_ERROR")
        assert exc.error_code == "CUSTOM_ERROR"

    def test_feather_exception_auto_error_code(self):
        """FeatherException auto-generates error_code from class name."""
        from feather import FeatherException
        exc = FeatherException("Test error")
        assert exc.error_code == "FEATHEREXCEPTION"

    def test_validation_error_has_field(self):
        """ValidationError has field attribute."""
        from feather import ValidationError
        exc = ValidationError("Invalid", field="email")
        assert exc.field == "email"

    def test_not_found_error_has_resource_type(self):
        """NotFoundError has resource_type attribute."""
        from feather import NotFoundError
        exc = NotFoundError("User", "123")
        assert exc.resource_type == "User"
        assert exc.resource_id == "123"


class TestExceptionStatusCodes:
    """Test that exceptions have correct HTTP status codes."""

    def test_validation_error_is_400(self):
        """ValidationError returns 400 Bad Request."""
        from feather import ValidationError
        exc = ValidationError("Invalid input")
        assert exc.status_code == 400

    def test_authentication_error_is_401(self):
        """AuthenticationError returns 401 Unauthorized."""
        from feather import AuthenticationError
        exc = AuthenticationError()
        assert exc.status_code == 401

    def test_authorization_error_is_403(self):
        """AuthorizationError returns 403 Forbidden."""
        from feather import AuthorizationError
        exc = AuthorizationError()
        assert exc.status_code == 403

    def test_not_found_error_is_404(self):
        """NotFoundError returns 404 Not Found."""
        from feather import NotFoundError
        exc = NotFoundError("Resource")
        assert exc.status_code == 404

    def test_conflict_error_is_409(self):
        """ConflictError returns 409 Conflict."""
        from feather import ConflictError
        exc = ConflictError("Already exists")
        assert exc.status_code == 409

    def test_storage_error_is_500(self):
        """StorageError returns 500 Internal Server Error."""
        from feather import StorageError
        exc = StorageError()
        assert exc.status_code == 500

    def test_database_error_is_500(self):
        """DatabaseError returns 500 Internal Server Error."""
        from feather import DatabaseError
        exc = DatabaseError()
        assert exc.status_code == 500

    def test_account_pending_error_is_403(self):
        """AccountPendingError returns 403 Forbidden."""
        from feather.exceptions import AccountPendingError
        exc = AccountPendingError()
        assert exc.status_code == 403

    def test_account_suspended_error_is_403(self):
        """AccountSuspendedError returns 403 Forbidden."""
        from feather.exceptions import AccountSuspendedError
        exc = AccountSuspendedError()
        assert exc.status_code == 403


class TestExceptionErrorCodes:
    """Test that exceptions have correct error codes."""

    def test_validation_error_code(self):
        """ValidationError has VALIDATION_ERROR code."""
        from feather import ValidationError
        exc = ValidationError("Invalid")
        assert exc.error_code == "VALIDATION_ERROR"

    def test_authentication_error_code(self):
        """AuthenticationError has AUTHENTICATION_ERROR code."""
        from feather import AuthenticationError
        exc = AuthenticationError()
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_authorization_error_code(self):
        """AuthorizationError has AUTHORIZATION_ERROR code."""
        from feather import AuthorizationError
        exc = AuthorizationError()
        assert exc.error_code == "AUTHORIZATION_ERROR"

    def test_not_found_error_code(self):
        """NotFoundError has NOT_FOUND code."""
        from feather import NotFoundError
        exc = NotFoundError("Resource")
        assert exc.error_code == "NOT_FOUND"

    def test_conflict_error_code(self):
        """ConflictError has CONFLICT code."""
        from feather import ConflictError
        exc = ConflictError("Already exists")
        assert exc.error_code == "CONFLICT"

    def test_account_pending_error_code(self):
        """AccountPendingError has ACCOUNT_PENDING code."""
        from feather.exceptions import AccountPendingError
        exc = AccountPendingError()
        assert exc.error_code == "ACCOUNT_PENDING"

    def test_account_suspended_error_code(self):
        """AccountSuspendedError has ACCOUNT_SUSPENDED code."""
        from feather.exceptions import AccountSuspendedError
        exc = AccountSuspendedError()
        assert exc.error_code == "ACCOUNT_SUSPENDED"


class TestExceptionStringRepresentation:
    """Test exception string representation."""

    def test_str_returns_message(self):
        """str(exception) returns the message."""
        from feather import ValidationError
        exc = ValidationError("Email is required")
        assert str(exc) == "Email is required"

    def test_not_found_message_format_with_id(self):
        """NotFoundError formats message with resource type and ID."""
        from feather import NotFoundError
        exc = NotFoundError("User", "123")
        assert exc.message == "User not found: 123"

    def test_not_found_message_format_without_id(self):
        """NotFoundError formats message with just resource type."""
        from feather import NotFoundError
        exc = NotFoundError("User")
        assert exc.message == "User not found"


class TestBuildErrorResponse:
    """Test build_error_response function."""

    def test_has_success_false(self):
        """Response has success: false."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="TEST_ERROR",
            message="Test message",
            status_code=400,
        )
        assert response["success"] is False

    def test_has_error_object(self):
        """Response has error object with code and message."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="VALIDATION_ERROR",
            message="Email required",
            status_code=400,
        )
        assert response["error"]["code"] == "VALIDATION_ERROR"
        assert response["error"]["message"] == "Email required"

    def test_has_null_data(self):
        """Response has data: null for errors."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="TEST_ERROR",
            message="Test",
            status_code=400,
        )
        assert response["data"] is None

    def test_has_meta_timestamp(self):
        """Response has meta.timestamp in ISO format."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="TEST_ERROR",
            message="Test",
            status_code=400,
        )
        assert "meta" in response
        assert "timestamp" in response["meta"]
        # Should be valid ISO format
        datetime.fromisoformat(response["meta"]["timestamp"].replace('Z', '+00:00'))

    def test_includes_request_id(self):
        """Response includes request_id in meta when provided."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="TEST_ERROR",
            message="Test",
            status_code=400,
            request_id="abc-123",
        )
        assert response["meta"]["request_id"] == "abc-123"

    def test_includes_field_for_validation(self):
        """Response includes field for validation errors."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="VALIDATION_ERROR",
            message="Email required",
            status_code=400,
            field="email",
        )
        assert response["error"]["field"] == "email"

    def test_field_not_included_when_none(self):
        """Response doesn't include field when not provided."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="NOT_FOUND",
            message="Resource not found",
            status_code=404,
        )
        assert "field" not in response["error"]


class TestBuildSuccessResponse:
    """Test build_success_response function."""

    def test_has_success_true(self):
        """Response has success: true."""
        from feather.core.error_handlers import build_success_response

        response = build_success_response(data={"id": "123"})
        assert response["success"] is True

    def test_has_data(self):
        """Response includes provided data."""
        from feather.core.error_handlers import build_success_response

        data = {"user": {"id": "123", "email": "test@example.com"}}
        response = build_success_response(data=data)
        assert response["data"] == data

    def test_has_null_error(self):
        """Response has error: null for success."""
        from feather.core.error_handlers import build_success_response

        response = build_success_response(data={})
        assert response["error"] is None

    def test_has_meta_timestamp(self):
        """Response has meta.timestamp."""
        from feather.core.error_handlers import build_success_response

        response = build_success_response(data={})
        assert "meta" in response
        assert "timestamp" in response["meta"]

    def test_includes_message(self):
        """Response includes message when provided."""
        from feather.core.error_handlers import build_success_response

        response = build_success_response(data={}, message="Created successfully")
        assert response["message"] == "Created successfully"

    def test_includes_request_id(self):
        """Response includes request_id when provided."""
        from feather.core.error_handlers import build_success_response

        response = build_success_response(data={}, request_id="xyz-789")
        assert response["meta"]["request_id"] == "xyz-789"


class TestResponseFormat:
    """Test the overall response format matches expectations."""

    def test_error_response_structure(self):
        """Error response has expected structure."""
        from feather.core.error_handlers import build_error_response

        response = build_error_response(
            code="VALIDATION_ERROR",
            message="Email is required",
            status_code=400,
            request_id="req-123",
            field="email",
        )

        # Check top-level keys
        assert set(response.keys()) == {"success", "data", "error", "meta"}

        # Check error structure
        assert set(response["error"].keys()) == {"code", "message", "field"}

        # Check meta structure
        assert "timestamp" in response["meta"]
        assert "request_id" in response["meta"]

    def test_success_response_structure(self):
        """Success response has expected structure."""
        from feather.core.error_handlers import build_success_response

        response = build_success_response(
            data={"id": "123"},
            message="Success",
            request_id="req-456",
        )

        # Check top-level keys
        assert "success" in response
        assert "data" in response
        assert "error" in response
        assert "meta" in response
        assert "message" in response
