"""0.9.8 deprecation shims.

Every intentional break in this release either keeps working or warns.
Nothing changes silently.
"""

import warnings

import pytest

pytestmark = pytest.mark.unit


class TestSingletonNames:
    """The module-level backend singletons became a per-app registry."""

    def test_queue_instance_warns_and_returns_the_current_queue(self):
        import feather.jobs as jobs_module
        from feather.jobs import get_queue

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = jobs_module._queue_instance

        assert value is get_queue()
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        assert "per-app registry" in str(caught[0].message)

    def test_cache_instance_warns_and_returns_the_current_cache(self):
        import feather.cache as cache_module
        from feather.cache import get_cache

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = cache_module._cache_instance

        assert value is get_cache()
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_rate_limiter_warns_and_returns_the_current_limiter(self):
        import feather.auth.decorators as decorators
        from feather.auth.decorators import get_rate_limiter

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = decorators._rate_limiter

        assert value is get_rate_limiter()
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_unknown_attributes_still_raise_attribute_error(self):
        import feather.cache as cache_module
        import feather.jobs as jobs_module

        for module in (jobs_module, cache_module):
            with pytest.raises(AttributeError):
                module.definitely_not_a_real_attribute


class TestSuspendedVersusPending:
    """A model with no approved_at column has no approval workflow."""

    def test_model_without_approved_at_is_suspended_not_pending(self):
        from feather.auth.tenancy import require_active_user
        from feather.exceptions import AccountSuspendedError

        class UserWithoutApproval:
            is_active = False

        with pytest.raises(AccountSuspendedError):
            require_active_user(UserWithoutApproval())

    def test_null_approved_at_is_still_pending(self):
        from feather.auth.tenancy import require_active_user
        from feather.exceptions import AccountPendingError

        class PendingUser:
            is_active = False
            approved_at = None

        with pytest.raises(AccountPendingError):
            require_active_user(PendingUser())

    def test_set_approved_at_is_suspended(self):
        from feather.auth.tenancy import require_active_user
        from feather.exceptions import AccountSuspendedError

        class SuspendedUser:
            is_active = False
            approved_at = "2026-01-01"

        with pytest.raises(AccountSuspendedError):
            require_active_user(SuspendedUser())

    def test_active_user_passes(self):
        from feather.auth.tenancy import require_active_user

        class ActiveUser:
            is_active = True
            approved_at = None

        require_active_user(ActiveUser())

    def test_model_without_is_active_is_treated_as_active(self):
        from feather.auth.tenancy import require_active_user

        class PlainUser:
            pass

        require_active_user(PlainUser())
