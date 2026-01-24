"""Contract tests for exception types.

These tests ensure the exception hierarchy and interfaces remain stable.
Changes to exception attributes, status codes, or constructor signatures
would be breaking changes.
"""

import pytest

pytestmark = pytest.mark.api_contract


class TestExceptionHierarchy:
    """Verify exception inheritance hierarchy."""

    def test_validation_error_inherits_feather_exception(self):
        """ValidationError must inherit from FeatherException."""
        from feather import ValidationError, FeatherException
        assert issubclass(ValidationError, FeatherException)

    def test_authentication_error_inherits_feather_exception(self):
        """AuthenticationError must inherit from FeatherException."""
        from feather import AuthenticationError, FeatherException
        assert issubclass(AuthenticationError, FeatherException)

    def test_authorization_error_inherits_feather_exception(self):
        """AuthorizationError must inherit from FeatherException."""
        from feather import AuthorizationError, FeatherException
        assert issubclass(AuthorizationError, FeatherException)

    def test_not_found_error_inherits_feather_exception(self):
        """NotFoundError must inherit from FeatherException."""
        from feather import NotFoundError, FeatherException
        assert issubclass(NotFoundError, FeatherException)

    def test_conflict_error_inherits_feather_exception(self):
        """ConflictError must inherit from FeatherException."""
        from feather import ConflictError, FeatherException
        assert issubclass(ConflictError, FeatherException)

    def test_storage_error_inherits_feather_exception(self):
        """StorageError must inherit from FeatherException."""
        from feather import StorageError, FeatherException
        assert issubclass(StorageError, FeatherException)

    def test_database_error_inherits_feather_exception(self):
        """DatabaseError must inherit from FeatherException."""
        from feather import DatabaseError, FeatherException
        assert issubclass(DatabaseError, FeatherException)

    def test_feather_exception_inherits_exception(self):
        """FeatherException must inherit from Exception."""
        from feather import FeatherException
        assert issubclass(FeatherException, Exception)

    def test_account_pending_error_inherits_authorization_error(self):
        """AccountPendingError must inherit from AuthorizationError."""
        from feather.exceptions import AccountPendingError, AuthorizationError
        assert issubclass(AccountPendingError, AuthorizationError)

    def test_account_suspended_error_inherits_authorization_error(self):
        """AccountSuspendedError must inherit from AuthorizationError."""
        from feather.exceptions import AccountSuspendedError, AuthorizationError
        assert issubclass(AccountSuspendedError, AuthorizationError)


class TestFeatherExceptionAttributes:
    """Verify FeatherException has expected attributes."""

    def test_has_message_attribute(self):
        """FeatherException must have message attribute."""
        from feather import FeatherException
        exc = FeatherException("Test error")
        assert hasattr(exc, 'message')
        assert exc.message == "Test error"

    def test_has_status_code_attribute(self):
        """FeatherException must have status_code attribute."""
        from feather import FeatherException
        exc = FeatherException("Test error")
        assert hasattr(exc, 'status_code')
        assert isinstance(exc.status_code, int)

    def test_has_error_code_attribute(self):
        """FeatherException must have error_code attribute."""
        from feather import FeatherException
        exc = FeatherException("Test error")
        assert hasattr(exc, 'error_code')

    def test_default_status_code_is_500(self):
        """FeatherException default status code must be 500."""
        from feather import FeatherException
        exc = FeatherException("Test error")
        assert exc.status_code == 500


class TestValidationErrorContract:
    """Verify ValidationError interface."""

    def test_status_code_is_400(self):
        """ValidationError status code must be 400."""
        from feather import ValidationError
        exc = ValidationError("Invalid input")
        assert exc.status_code == 400

    def test_error_code(self):
        """ValidationError error_code must be VALIDATION_ERROR."""
        from feather import ValidationError
        exc = ValidationError("Invalid input")
        assert exc.error_code == "VALIDATION_ERROR"

    def test_has_field_attribute(self):
        """ValidationError must have field attribute."""
        from feather import ValidationError
        exc = ValidationError("Email required", field="email")
        assert hasattr(exc, 'field')
        assert exc.field == "email"

    def test_field_defaults_to_none(self):
        """ValidationError field must default to None."""
        from feather import ValidationError
        exc = ValidationError("Invalid input")
        assert exc.field is None

    def test_constructor_signature(self):
        """ValidationError constructor must accept message and field."""
        from feather import ValidationError
        # With both parameters
        exc = ValidationError("Error", field="name")
        assert exc.message == "Error"
        assert exc.field == "name"


class TestAuthenticationErrorContract:
    """Verify AuthenticationError interface."""

    def test_status_code_is_401(self):
        """AuthenticationError status code must be 401."""
        from feather import AuthenticationError
        exc = AuthenticationError()
        assert exc.status_code == 401

    def test_error_code(self):
        """AuthenticationError error_code must be AUTHENTICATION_ERROR."""
        from feather import AuthenticationError
        exc = AuthenticationError()
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_default_message(self):
        """AuthenticationError must have default message."""
        from feather import AuthenticationError
        exc = AuthenticationError()
        assert exc.message == "Authentication required"

    def test_custom_message(self):
        """AuthenticationError must accept custom message."""
        from feather import AuthenticationError
        exc = AuthenticationError("Session expired")
        assert exc.message == "Session expired"


class TestAuthorizationErrorContract:
    """Verify AuthorizationError interface."""

    def test_status_code_is_403(self):
        """AuthorizationError status code must be 403."""
        from feather import AuthorizationError
        exc = AuthorizationError()
        assert exc.status_code == 403

    def test_error_code(self):
        """AuthorizationError error_code must be AUTHORIZATION_ERROR."""
        from feather import AuthorizationError
        exc = AuthorizationError()
        assert exc.error_code == "AUTHORIZATION_ERROR"

    def test_default_message(self):
        """AuthorizationError must have default message."""
        from feather import AuthorizationError
        exc = AuthorizationError()
        assert exc.message == "Permission denied"

    def test_custom_message(self):
        """AuthorizationError must accept custom message."""
        from feather import AuthorizationError
        exc = AuthorizationError("Admin only")
        assert exc.message == "Admin only"


class TestNotFoundErrorContract:
    """Verify NotFoundError interface."""

    def test_status_code_is_404(self):
        """NotFoundError status code must be 404."""
        from feather import NotFoundError
        exc = NotFoundError("User")
        assert exc.status_code == 404

    def test_error_code(self):
        """NotFoundError error_code must be NOT_FOUND."""
        from feather import NotFoundError
        exc = NotFoundError("User")
        assert exc.error_code == "NOT_FOUND"

    def test_has_resource_type_attribute(self):
        """NotFoundError must have resource_type attribute."""
        from feather import NotFoundError
        exc = NotFoundError("User")
        assert hasattr(exc, 'resource_type')
        assert exc.resource_type == "User"

    def test_has_resource_id_attribute(self):
        """NotFoundError must have resource_id attribute."""
        from feather import NotFoundError
        exc = NotFoundError("User", "123")
        assert hasattr(exc, 'resource_id')
        assert exc.resource_id == "123"

    def test_resource_id_defaults_to_none(self):
        """NotFoundError resource_id must default to None."""
        from feather import NotFoundError
        exc = NotFoundError("User")
        assert exc.resource_id is None

    def test_message_without_id(self):
        """NotFoundError message format without ID."""
        from feather import NotFoundError
        exc = NotFoundError("User")
        assert exc.message == "User not found"

    def test_message_with_id(self):
        """NotFoundError message format with ID."""
        from feather import NotFoundError
        exc = NotFoundError("User", "123")
        assert exc.message == "User not found: 123"


class TestConflictErrorContract:
    """Verify ConflictError interface."""

    def test_status_code_is_409(self):
        """ConflictError status code must be 409."""
        from feather import ConflictError
        exc = ConflictError("Already exists")
        assert exc.status_code == 409

    def test_error_code(self):
        """ConflictError error_code must be CONFLICT."""
        from feather import ConflictError
        exc = ConflictError("Already exists")
        assert exc.error_code == "CONFLICT"

    def test_message(self):
        """ConflictError must store message."""
        from feather import ConflictError
        exc = ConflictError("Email already registered")
        assert exc.message == "Email already registered"


class TestStorageErrorContract:
    """Verify StorageError interface."""

    def test_status_code_is_500(self):
        """StorageError status code must be 500."""
        from feather import StorageError
        exc = StorageError()
        assert exc.status_code == 500

    def test_error_code(self):
        """StorageError error_code must be STORAGE_ERROR."""
        from feather import StorageError
        exc = StorageError()
        assert exc.error_code == "STORAGE_ERROR"

    def test_default_message(self):
        """StorageError must have default message."""
        from feather import StorageError
        exc = StorageError()
        assert exc.message == "Storage operation failed"

    def test_custom_message(self):
        """StorageError must accept custom message."""
        from feather import StorageError
        exc = StorageError("Upload failed")
        assert exc.message == "Upload failed"


class TestDatabaseErrorContract:
    """Verify DatabaseError interface."""

    def test_status_code_is_500(self):
        """DatabaseError status code must be 500."""
        from feather import DatabaseError
        exc = DatabaseError()
        assert exc.status_code == 500

    def test_error_code(self):
        """DatabaseError error_code must be DATABASE_ERROR."""
        from feather import DatabaseError
        exc = DatabaseError()
        assert exc.error_code == "DATABASE_ERROR"

    def test_default_message(self):
        """DatabaseError must have default message."""
        from feather import DatabaseError
        exc = DatabaseError()
        assert exc.message == "Database operation failed"

    def test_custom_message(self):
        """DatabaseError must accept custom message."""
        from feather import DatabaseError
        exc = DatabaseError("Connection lost")
        assert exc.message == "Connection lost"


class TestRateLimitErrorContract:
    """Verify RateLimitError interface (from feather.exceptions)."""

    def test_exists_in_exceptions_module(self):
        """RateLimitError must be importable from feather.exceptions."""
        from feather.exceptions import RateLimitError
        assert RateLimitError is not None

    def test_status_code_is_429(self):
        """RateLimitError status code must be 429."""
        from feather.exceptions import RateLimitError
        exc = RateLimitError()
        assert exc.status_code == 429

    def test_error_code(self):
        """RateLimitError error_code must be RATE_LIMIT_ERROR."""
        from feather.exceptions import RateLimitError
        exc = RateLimitError()
        assert exc.error_code == "RATE_LIMIT_ERROR"

    def test_default_message(self):
        """RateLimitError must have default message."""
        from feather.exceptions import RateLimitError
        exc = RateLimitError()
        assert exc.message == "Too many requests"


class TestAccountPendingErrorContract:
    """Verify AccountPendingError interface."""

    def test_exists_in_exceptions_module(self):
        """AccountPendingError must be importable from feather.exceptions."""
        from feather.exceptions import AccountPendingError
        assert AccountPendingError is not None

    def test_inherits_from_authorization_error(self):
        """AccountPendingError must inherit from AuthorizationError."""
        from feather.exceptions import AccountPendingError, AuthorizationError
        assert issubclass(AccountPendingError, AuthorizationError)

    def test_status_code_is_403(self):
        """AccountPendingError status code must be 403."""
        from feather.exceptions import AccountPendingError
        exc = AccountPendingError()
        assert exc.status_code == 403

    def test_error_code(self):
        """AccountPendingError error_code must be ACCOUNT_PENDING."""
        from feather.exceptions import AccountPendingError
        exc = AccountPendingError()
        assert exc.error_code == "ACCOUNT_PENDING"

    def test_default_message(self):
        """AccountPendingError must have default message."""
        from feather.exceptions import AccountPendingError
        exc = AccountPendingError()
        assert exc.message == "Account pending approval"

    def test_custom_message(self):
        """AccountPendingError must accept custom message."""
        from feather.exceptions import AccountPendingError
        exc = AccountPendingError("Your account is awaiting review")
        assert exc.message == "Your account is awaiting review"


class TestAccountSuspendedErrorContract:
    """Verify AccountSuspendedError interface."""

    def test_exists_in_exceptions_module(self):
        """AccountSuspendedError must be importable from feather.exceptions."""
        from feather.exceptions import AccountSuspendedError
        assert AccountSuspendedError is not None

    def test_inherits_from_authorization_error(self):
        """AccountSuspendedError must inherit from AuthorizationError."""
        from feather.exceptions import AccountSuspendedError, AuthorizationError
        assert issubclass(AccountSuspendedError, AuthorizationError)

    def test_status_code_is_403(self):
        """AccountSuspendedError status code must be 403."""
        from feather.exceptions import AccountSuspendedError
        exc = AccountSuspendedError()
        assert exc.status_code == 403

    def test_error_code(self):
        """AccountSuspendedError error_code must be ACCOUNT_SUSPENDED."""
        from feather.exceptions import AccountSuspendedError
        exc = AccountSuspendedError()
        assert exc.error_code == "ACCOUNT_SUSPENDED"

    def test_default_message(self):
        """AccountSuspendedError must have default message."""
        from feather.exceptions import AccountSuspendedError
        exc = AccountSuspendedError()
        assert exc.message == "Account suspended"

    def test_custom_message(self):
        """AccountSuspendedError must accept custom message."""
        from feather.exceptions import AccountSuspendedError
        exc = AccountSuspendedError("Your account has been deactivated")
        assert exc.message == "Your account has been deactivated"


class TestExceptionRaising:
    """Verify exceptions can be raised and caught."""

    def test_can_raise_validation_error(self):
        """ValidationError can be raised and caught."""
        from feather import ValidationError, FeatherException

        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Test", field="test")

        assert exc_info.value.field == "test"

    def test_can_catch_as_feather_exception(self):
        """All exceptions can be caught as FeatherException."""
        from feather import ValidationError, NotFoundError, FeatherException

        for exc_class in [ValidationError, NotFoundError]:
            with pytest.raises(FeatherException):
                if exc_class == ValidationError:
                    raise exc_class("Test")
                else:
                    raise exc_class("Resource")

    def test_exception_string_representation(self):
        """Exceptions should have string representation via message."""
        from feather import ValidationError
        exc = ValidationError("Invalid email")
        assert str(exc) == "Invalid email"
