"""Contract tests for decorator signatures.

These tests ensure decorators accept the expected parameters and can be
applied to functions without errors. If parameters are removed or renamed,
these tests will fail, indicating a breaking change.
"""

import pytest

pytestmark = pytest.mark.api_contract


class TestJobDecoratorSignature:
    """Verify @job decorator accepts expected parameters."""

    def test_job_no_params(self):
        """@job can be used without parameters."""
        from feather import job

        @job
        def basic_job():
            pass

        assert hasattr(basic_job, 'enqueue')

    def test_job_with_concurrency(self):
        """@job accepts concurrency parameter."""
        from feather import job

        @job(concurrency=2)
        def concurrent_job():
            pass

        assert hasattr(concurrent_job, 'enqueue')

    def test_job_with_retry(self):
        """@job accepts retry parameter."""
        from feather import job

        @job(retry=3)
        def retry_job():
            pass

        assert hasattr(retry_job, 'enqueue')

    def test_job_with_timeout(self):
        """@job accepts timeout parameter."""
        from feather import job

        @job(timeout=60)
        def timeout_job():
            pass

        assert hasattr(timeout_job, 'enqueue')

    def test_job_with_all_params(self):
        """@job accepts all parameters together."""
        from feather import job

        @job(concurrency=2, retry=3, timeout=60)
        def full_job():
            pass

        assert hasattr(full_job, 'enqueue')


class TestScheduledDecoratorSignature:
    """Verify @scheduled decorator accepts expected parameters."""

    def test_scheduled_with_cron(self):
        """@scheduled accepts cron parameter."""
        from feather import scheduled

        @scheduled(cron='0 9 * * *')
        def daily_job():
            pass

        assert callable(daily_job)

    def test_scheduled_with_interval(self):
        """@scheduled accepts interval parameter."""
        from feather import scheduled

        @scheduled(interval=3600)
        def hourly_job():
            pass

        assert callable(hourly_job)


class TestRoleRequiredSignature:
    """Verify @role_required decorator accepts expected parameters."""

    def test_role_required_single_role(self):
        """@role_required accepts a single role."""
        from feather import role_required

        @role_required('admin')
        def admin_only():
            pass

        assert callable(admin_only)

    def test_role_required_multiple_roles_as_list(self):
        """@role_required accepts list of roles."""
        from feather import role_required

        @role_required(['editor', 'admin'])
        def editor_or_admin():
            pass

        assert callable(editor_or_admin)

    def test_role_required_multiple_roles_as_set(self):
        """@role_required accepts set of roles."""
        from feather import role_required

        @role_required({'editor', 'admin'})
        def editor_or_admin():
            pass

        assert callable(editor_or_admin)


class TestPermissionRequiredSignature:
    """Verify @permission_required decorator accepts expected parameters."""

    def test_permission_required_single(self):
        """@permission_required accepts a single permission."""
        from feather import permission_required

        @permission_required('users.create')
        def create_user():
            pass

        assert callable(create_user)


class TestRateLimitSignature:
    """Verify @rate_limit decorator accepts expected parameters."""

    def test_rate_limit_basic(self):
        """@rate_limit accepts limit and period."""
        from feather import rate_limit

        @rate_limit(10, 60)
        def limited_route():
            pass

        assert callable(limited_route)

    def test_rate_limit_with_key(self):
        """@rate_limit accepts key parameter."""
        from feather import rate_limit

        @rate_limit(10, 60, key='user')
        def user_limited():
            pass

        assert callable(user_limited)

    def test_rate_limit_with_message(self):
        """@rate_limit accepts message parameter."""
        from feather import rate_limit

        @rate_limit(10, 60, message='Too many requests')
        def custom_message():
            pass

        assert callable(custom_message)


class TestCachedDecoratorSignature:
    """Verify @cached decorator accepts expected parameters."""

    def test_cached_with_ttl(self):
        """@cached accepts ttl parameter."""
        from feather import cached

        @cached(ttl=60)
        def cached_func():
            pass

        assert callable(cached_func)


class TestCacheResponseSignature:
    """Verify @cache_response decorator accepts expected parameters."""

    def test_cache_response_with_ttl(self):
        """@cache_response accepts ttl parameter."""
        from feather import cache_response

        @cache_response(ttl=300)
        def cached_route():
            pass

        assert callable(cached_route)

    def test_cache_response_with_key(self):
        """@cache_response accepts key parameter."""
        from feather import cache_response

        @cache_response(ttl=300, key='custom:{user_id}')
        def keyed_cache():
            pass

        assert callable(keyed_cache)


class TestTransactionalSignature:
    """Verify @transactional decorator works."""

    def test_transactional_no_params(self):
        """@transactional can be used without parameters."""
        from feather import transactional

        @transactional
        def transactional_func():
            pass

        assert callable(transactional_func)


class TestSingletonSignature:
    """Verify @singleton decorator works."""

    def test_singleton_on_class(self):
        """@singleton can be applied to a class."""
        from feather import singleton, Service

        @singleton
        class SingletonService(Service):
            pass

        assert SingletonService is not None


class TestListenDecoratorSignature:
    """Verify @listen decorator accepts expected parameters."""

    def test_listen_basic(self):
        """@listen accepts event class."""
        from feather import listen
        from feather.events import Event

        class TestEvent(Event):
            pass

        @listen(TestEvent)
        def handler(event):
            pass

        assert callable(handler)

    def test_listen_with_async(self):
        """@listen accepts async_ parameter."""
        from feather import listen
        from feather.events import Event

        class TestEvent(Event):
            pass

        @listen(TestEvent, async_=True)
        def async_handler(event):
            pass

        assert callable(async_handler)


class TestInjectDecoratorSignature:
    """Verify @inject decorator accepts service classes."""

    def test_inject_single_service(self):
        """@inject accepts a single service class."""
        from feather import inject, Service

        class TestService(Service):
            pass

        @inject(TestService)
        def route_with_service(test_service):
            pass

        assert callable(route_with_service)

    def test_inject_multiple_services(self):
        """@inject accepts multiple service classes."""
        from feather import inject, Service

        class ServiceA(Service):
            pass

        class ServiceB(Service):
            pass

        @inject(ServiceA, ServiceB)
        def route_with_services(service_a, service_b):
            pass

        assert callable(route_with_services)
