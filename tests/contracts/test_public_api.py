"""Contract tests for public API exports.

These tests ensure all documented exports from the feather package exist
and are importable. If any of these tests fail, it indicates a breaking
change in the public API.

Breaking changes should only happen in major version bumps (x.0.0).
"""

import pytest

pytestmark = pytest.mark.api_contract


class TestCoreExports:
    """Verify core exports from feather package."""

    def test_feather_class(self):
        """Feather application class must be importable."""
        from feather import Feather
        assert Feather is not None

    def test_route_blueprints(self):
        """Route blueprints must be importable."""
        from feather import api, page
        assert api is not None
        assert page is not None

    def test_inject_decorator(self):
        """Inject decorator must be importable."""
        from feather import inject
        assert callable(inject)

    def test_auth_required_decorator(self):
        """Auth required decorator must be importable."""
        from feather import auth_required
        assert callable(auth_required)

    def test_csrf_exempt_decorator(self):
        """CSRF exempt decorator must be importable."""
        from feather import csrf_exempt
        assert callable(csrf_exempt)


class TestServiceExports:
    """Verify service layer exports."""

    def test_service_class(self):
        """Service base class must be importable."""
        from feather import Service
        assert Service is not None

    def test_transactional_decorator(self):
        """Transactional decorator must be importable."""
        from feather import transactional
        assert callable(transactional)

    def test_singleton_decorator(self):
        """Singleton decorator must be importable."""
        from feather import singleton
        assert callable(singleton)


class TestAuthExports:
    """Verify authentication/authorization exports."""

    def test_admin_required(self):
        """Admin required decorator must be importable."""
        from feather import admin_required
        assert callable(admin_required)

    def test_role_required(self):
        """Role required decorator must be importable."""
        from feather import role_required
        assert callable(role_required)

    def test_permission_required(self):
        """Permission required decorator must be importable."""
        from feather import permission_required
        assert callable(permission_required)

    def test_platform_admin_required(self):
        """Platform admin required decorator must be importable."""
        from feather import platform_admin_required
        assert callable(platform_admin_required)

    def test_rate_limit(self):
        """Rate limit decorator must be importable."""
        from feather import rate_limit
        assert callable(rate_limit)


class TestTenancyExports:
    """Verify multi-tenancy exports."""

    def test_get_current_tenant_id(self):
        """Get current tenant ID function must be importable."""
        from feather import get_current_tenant_id
        assert callable(get_current_tenant_id)

    def test_tenant_required(self):
        """Tenant required decorator must be importable."""
        from feather import tenant_required
        assert callable(tenant_required)


class TestDatabaseExports:
    """Verify database exports."""

    def test_db_instance(self):
        """SQLAlchemy db instance must be importable."""
        from feather import db
        assert db is not None

    def test_model_class(self):
        """Model base class must be importable."""
        from feather import Model
        assert Model is not None

    def test_uuid_mixin(self):
        """UUIDMixin must be importable."""
        from feather import UUIDMixin
        assert UUIDMixin is not None

    def test_timestamp_mixin(self):
        """TimestampMixin must be importable."""
        from feather import TimestampMixin
        assert TimestampMixin is not None

    def test_soft_delete_mixin(self):
        """SoftDeleteMixin must be importable."""
        from feather import SoftDeleteMixin
        assert SoftDeleteMixin is not None

    def test_ordering_mixin(self):
        """OrderingMixin must be importable."""
        from feather import OrderingMixin
        assert OrderingMixin is not None

    def test_tenant_scoped_mixin(self):
        """TenantScopedMixin must be importable."""
        from feather import TenantScopedMixin
        assert TenantScopedMixin is not None

    def test_paginate(self):
        """Paginate function must be importable."""
        from feather import paginate
        assert callable(paginate)

    def test_paginated_result(self):
        """PaginatedResult class must be importable."""
        from feather import PaginatedResult
        assert PaginatedResult is not None


class TestDatabaseModuleExports:
    """Verify exports from feather.db module."""

    def test_db_operation_context_manager(self):
        """db_operation context manager must be importable from feather.db."""
        from feather.db import db_operation
        assert db_operation is not None

    def test_migrate_instance(self):
        """Migrate instance must be importable from feather.db."""
        from feather.db import migrate
        assert migrate is not None


class TestEventExports:
    """Verify event system exports."""

    def test_dispatch(self):
        """Dispatch function must be importable."""
        from feather import dispatch
        assert callable(dispatch)

    def test_listen(self):
        """Listen decorator must be importable."""
        from feather import listen
        assert callable(listen)


class TestStorageExports:
    """Verify storage exports."""

    def test_get_storage(self):
        """Get storage function must be importable."""
        from feather import get_storage
        assert callable(get_storage)


class TestCacheExports:
    """Verify cache exports."""

    def test_get_cache(self):
        """Get cache function must be importable."""
        from feather import get_cache
        assert callable(get_cache)

    def test_cached_decorator(self):
        """Cached decorator must be importable."""
        from feather import cached
        assert callable(cached)

    def test_cache_response_decorator(self):
        """Cache response decorator must be importable."""
        from feather import cache_response
        assert callable(cache_response)


class TestJobsExports:
    """Verify background jobs exports."""

    def test_get_queue(self):
        """Get queue function must be importable."""
        from feather import get_queue
        assert callable(get_queue)

    def test_job_decorator(self):
        """Job decorator must be importable."""
        from feather import job
        assert callable(job)

    def test_scheduled_decorator(self):
        """Scheduled decorator must be importable."""
        from feather import scheduled
        assert callable(scheduled)

    def test_job_status_enum(self):
        """JobStatus enum must be importable from feather.jobs."""
        from feather.jobs import JobStatus
        assert JobStatus is not None
        # Verify expected statuses exist
        assert hasattr(JobStatus, 'QUEUED')
        assert hasattr(JobStatus, 'STARTED')
        assert hasattr(JobStatus, 'FINISHED')
        assert hasattr(JobStatus, 'FAILED')
        assert hasattr(JobStatus, 'SCHEDULED')
        assert hasattr(JobStatus, 'TIMEOUT')


class TestRequestTrackingExports:
    """Verify request tracking exports."""

    def test_get_request_id(self):
        """Get request ID function must be importable."""
        from feather import get_request_id
        assert callable(get_request_id)


class TestExceptionExports:
    """Verify exception exports."""

    def test_feather_exception(self):
        """FeatherException must be importable."""
        from feather import FeatherException
        assert issubclass(FeatherException, Exception)

    def test_validation_error(self):
        """ValidationError must be importable."""
        from feather import ValidationError
        assert issubclass(ValidationError, Exception)

    def test_authentication_error(self):
        """AuthenticationError must be importable."""
        from feather import AuthenticationError
        assert issubclass(AuthenticationError, Exception)

    def test_authorization_error(self):
        """AuthorizationError must be importable."""
        from feather import AuthorizationError
        assert issubclass(AuthorizationError, Exception)

    def test_not_found_error(self):
        """NotFoundError must be importable."""
        from feather import NotFoundError
        assert issubclass(NotFoundError, Exception)

    def test_conflict_error(self):
        """ConflictError must be importable."""
        from feather import ConflictError
        assert issubclass(ConflictError, Exception)

    def test_storage_error(self):
        """StorageError must be importable."""
        from feather import StorageError
        assert issubclass(StorageError, Exception)

    def test_database_error(self):
        """DatabaseError must be importable."""
        from feather import DatabaseError
        assert issubclass(DatabaseError, Exception)


class TestSerializerExports:
    """Verify serializer exports from feather.serializers."""

    def test_serializer_class(self):
        """Serializer class must be importable."""
        from feather.serializers import Serializer
        assert Serializer is not None

    def test_string_field(self):
        """StringField must be importable."""
        from feather.serializers import StringField
        assert StringField is not None

    def test_integer_field(self):
        """IntegerField must be importable."""
        from feather.serializers import IntegerField
        assert IntegerField is not None

    def test_float_field(self):
        """FloatField must be importable."""
        from feather.serializers import FloatField
        assert FloatField is not None

    def test_boolean_field(self):
        """BooleanField must be importable."""
        from feather.serializers import BooleanField
        assert BooleanField is not None

    def test_datetime_field(self):
        """DateTimeField must be importable."""
        from feather.serializers import DateTimeField
        assert DateTimeField is not None

    def test_nested_field(self):
        """NestedField must be importable."""
        from feather.serializers import NestedField
        assert NestedField is not None

    def test_method_field(self):
        """MethodField must be importable."""
        from feather.serializers import MethodField
        assert MethodField is not None


class TestHelperExports:
    """Verify helper function exports from feather.core.helpers."""

    def test_htmx_redirect(self):
        """htmx_redirect must be importable."""
        from feather.core.helpers import htmx_redirect
        assert callable(htmx_redirect)

    def test_htmx_refresh(self):
        """htmx_refresh must be importable."""
        from feather.core.helpers import htmx_refresh
        assert callable(htmx_refresh)

    def test_with_trigger(self):
        """with_trigger must be importable."""
        from feather.core.helpers import with_trigger
        assert callable(with_trigger)

    def test_feather_island_scripts(self):
        """feather_island_scripts must be importable."""
        from feather.core.helpers import feather_island_scripts
        assert callable(feather_island_scripts)


class TestVersionExport:
    """Verify version is accessible."""

    def test_version_string(self):
        """__version__ must be a string."""
        from feather import __version__
        assert isinstance(__version__, str)
        # Verify semver format (x.y.z)
        parts = __version__.split('.')
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)


# =============================================================================
# Decorator Signature Tests
# =============================================================================

class TestDecoratorSignatures:
    """Decorators must accept expected parameters."""

    def test_job_accepts_concurrency_and_retry(self):
        """@job accepts concurrency and retry parameters."""
        from feather import job

        @job(concurrency=2, retry=3)
        def test_func():
            pass

        assert callable(test_func)

    def test_role_required_accepts_single_role(self):
        """@role_required accepts a single role string."""
        from feather import role_required

        decorator = role_required('admin')
        assert callable(decorator)

    def test_role_required_accepts_list_of_roles(self):
        """@role_required accepts a list of roles."""
        from feather import role_required

        decorator = role_required(['admin', 'editor'])
        assert callable(decorator)

    def test_rate_limit_accepts_limit_and_period(self):
        """@rate_limit accepts limit and period parameters."""
        from feather import rate_limit

        decorator = rate_limit(100, 60)
        assert callable(decorator)

    def test_rate_limit_accepts_key_parameter(self):
        """@rate_limit accepts key parameter."""
        from feather import rate_limit

        decorator = rate_limit(100, 60, key='user')
        assert callable(decorator)

    def test_cached_accepts_ttl(self):
        """@cached accepts ttl parameter."""
        from feather import cached

        @cached(ttl=60)
        def test_func():
            pass

        assert callable(test_func)

    def test_cache_response_accepts_ttl_and_key(self):
        """@cache_response accepts ttl and key parameters."""
        from feather import cache_response

        decorator = cache_response(ttl=300, key='my_key')
        assert callable(decorator)

    def test_inject_accepts_service_classes(self):
        """@inject accepts service class arguments."""
        from feather import inject, Service

        class TestService(Service):
            pass

        decorator = inject(TestService)
        assert callable(decorator)

    def test_listen_accepts_event_class(self):
        """@listen accepts an event class."""
        from feather import listen
        from feather.events import Event

        class TestEvent(Event):
            pass

        @listen(TestEvent)
        def handler(event):
            pass

        assert callable(handler)

    def test_listen_accepts_async_parameter(self):
        """@listen accepts async_ parameter."""
        from feather import listen
        from feather.events import Event

        class TestEvent(Event):
            pass

        @listen(TestEvent, async_=True)
        def async_handler(event):
            pass

        assert callable(async_handler)

    def test_scheduled_accepts_cron(self):
        """@scheduled accepts cron parameter."""
        from feather import scheduled

        @scheduled(cron='0 9 * * *')
        def daily_task():
            pass

        assert callable(daily_task)

    def test_scheduled_accepts_interval(self):
        """@scheduled accepts interval parameter."""
        from feather import scheduled

        @scheduled(interval=3600)
        def hourly_task():
            pass

        assert callable(hourly_task)


# =============================================================================
# Exception Signature Tests
# =============================================================================

class TestExceptionSignatures:
    """Exceptions must accept expected parameters."""

    def test_validation_error_accepts_message_and_field(self):
        """ValidationError accepts message and field."""
        from feather import ValidationError

        error = ValidationError('Invalid email', field='email')
        assert error.message == 'Invalid email'
        assert error.field == 'email'

    def test_not_found_error_accepts_resource_and_id(self):
        """NotFoundError accepts resource_type and resource_id."""
        from feather import NotFoundError

        error = NotFoundError('User', 'user-123')
        assert 'User' in error.message
        assert 'user-123' in error.message

    def test_authentication_error_has_default_message(self):
        """AuthenticationError has a default message."""
        from feather import AuthenticationError

        error = AuthenticationError()
        assert error.message is not None
        assert len(error.message) > 0

    def test_authorization_error_has_default_message(self):
        """AuthorizationError has a default message."""
        from feather import AuthorizationError

        error = AuthorizationError()
        assert error.message is not None
        assert len(error.message) > 0

    def test_exceptions_have_status_code(self):
        """All Feather exceptions have a status_code attribute."""
        from feather import (
            ValidationError,
            AuthenticationError,
            AuthorizationError,
            NotFoundError,
            ConflictError,
            StorageError,
            DatabaseError,
        )

        assert hasattr(ValidationError('test'), 'status_code')
        assert hasattr(AuthenticationError(), 'status_code')
        assert hasattr(AuthorizationError(), 'status_code')
        assert hasattr(NotFoundError('Resource'), 'status_code')
        assert hasattr(ConflictError('conflict'), 'status_code')
        assert hasattr(StorageError(), 'status_code')
        assert hasattr(DatabaseError(), 'status_code')

    def test_exceptions_have_error_code(self):
        """All Feather exceptions have an error_code attribute."""
        from feather import (
            ValidationError,
            AuthenticationError,
            AuthorizationError,
            NotFoundError,
            ConflictError,
        )

        assert hasattr(ValidationError('test'), 'error_code')
        assert hasattr(AuthenticationError(), 'error_code')
        assert hasattr(AuthorizationError(), 'error_code')
        assert hasattr(NotFoundError('Resource'), 'error_code')
        assert hasattr(ConflictError('conflict'), 'error_code')


# =============================================================================
# __all__ Completeness Tests
# =============================================================================

class TestAllExports:
    """Verify __all__ matches actual exports."""

    def test_all_exports_are_importable(self):
        """Every item in __all__ is importable."""
        import feather

        for name in feather.__all__:
            assert hasattr(feather, name), f"'{name}' in __all__ but not importable"

    def test_all_contains_core_exports(self):
        """__all__ contains all core exports."""
        import feather

        core_exports = [
            'Feather', 'api', 'page', 'inject', 'auth_required', 'csrf_exempt',
            'Service', 'transactional', 'singleton',
            'db', 'Model',
            'dispatch', 'listen',
            'get_storage', 'get_cache', 'cached', 'cache_response',
            'get_queue', 'job', 'scheduled',
        ]

        for export in core_exports:
            assert export in feather.__all__, f"'{export}' missing from __all__"
