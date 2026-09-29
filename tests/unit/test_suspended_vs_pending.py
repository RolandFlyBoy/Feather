"""A user without an approval workflow is suspended, not pending."""

import pytest

pytestmark = pytest.mark.unit


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
