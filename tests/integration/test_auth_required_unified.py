"""`feather.auth_required` and `feather.auth.auth_required` are one decorator (0.9.8).

Before 0.9.8 the two import paths behaved differently for a suspended user:
the core one raised a plain AuthorizationError, the auth one raised
AccountSuspendedError, which is what the error handlers key on for the
suspended/pending redirects. Both paths must now behave identically.
"""

import pytest
from flask_login import UserMixin, login_user

from feather import Feather
from feather import auth_required as core_auth_required
from feather.auth import auth_required as auth_auth_required
from feather.db import db

pytestmark = pytest.mark.integration


class _AuthUnifiedUser(db.Model, UserMixin):
    __tablename__ = "auth_unified_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255))
    tenant_id = db.Column(db.String(64))
    active = db.Column(db.Boolean, default=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_active(self):
        return self.active


@pytest.fixture
def app(tmp_path):
    application = Feather(__name__)
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    application.config["SECRET_KEY"] = "test-secret"

    from feather.auth.setup import login_manager

    login_manager.init_app(application)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(_AuthUnifiedUser, int(user_id))

    @application.route("/test-login/<int:user_id>", methods=["POST"])
    def test_login(user_id):
        user = db.session.get(_AuthUnifiedUser, user_id)
        login_user(user, force=True)
        return {"ok": True}

    @application.route("/api/via-core")
    @core_auth_required
    def via_core():
        return {"ok": "core"}

    @application.route("/api/via-auth")
    @auth_auth_required
    def via_auth():
        return {"ok": "auth"}

    with application.app_context():
        db.create_all()
        from datetime import datetime, timezone

        db.session.add(
            _AuthUnifiedUser(
                id=1, email="ok@example.com", tenant_id="t1", active=True,
                approved_at=datetime.now(timezone.utc),
            )
        )
        db.session.add(
            _AuthUnifiedUser(
                id=2, email="suspended@example.com", tenant_id="t1", active=False,
                approved_at=datetime.now(timezone.utc),
            )
        )
        db.session.add(
            _AuthUnifiedUser(
                id=3, email="pending@example.com", tenant_id="t1", active=False,
                approved_at=None,
            )
        )
        db.session.commit()

    yield application

    with application.app_context():
        db.drop_all()
        db.session.remove()
        db.engine.dispose()


def _get_both(app, user_id):
    responses = {}
    for path in ("/api/via-core", "/api/via-auth"):
        client = app.test_client()
        client.post(f"/test-login/{user_id}")
        responses[path] = client.get(path)
    return responses


class TestSameDecorator:
    def test_core_export_is_the_tenancy_aware_decorator(self):
        assert core_auth_required is auth_auth_required

    def test_core_decorators_module_exports_the_same_object(self):
        from feather.core.decorators import auth_required as from_core_module

        assert from_core_module is auth_auth_required


class TestSuspendedUserSameEitherWay:
    def test_suspended_user_gets_the_same_status(self, app):
        responses = _get_both(app, 2)
        assert responses["/api/via-core"].status_code == responses["/api/via-auth"].status_code
        assert responses["/api/via-core"].status_code == 403

    def test_suspended_user_gets_the_same_error_code(self, app):
        responses = _get_both(app, 2)
        core = responses["/api/via-core"].get_json()["error"]
        other = responses["/api/via-auth"].get_json()["error"]
        assert core == other
        assert "suspended" in core["message"].lower()

    def test_pending_user_gets_the_same_error_code(self, app):
        responses = _get_both(app, 3)
        core = responses["/api/via-core"].get_json()["error"]
        other = responses["/api/via-auth"].get_json()["error"]
        assert core == other
        assert "pending" in core["message"].lower()

    def test_active_user_passes_through_both(self, app):
        responses = _get_both(app, 1)
        assert responses["/api/via-core"].status_code == 200
        assert responses["/api/via-auth"].status_code == 200

    def test_anonymous_user_gets_401_through_both(self, app):
        client = app.test_client()
        assert client.get("/api/via-core").status_code == 401
        assert client.get("/api/via-auth").status_code == 401


class TestRaisedExceptionTypes:
    def test_core_path_raises_account_suspended_error(self, app):
        """The exception type is what the pending/suspended redirects key on."""
        from feather.exceptions import AccountSuspendedError

        with app.test_request_context("/api/via-core"):
            from flask_login import login_user as _login

            user = db.session.get(_AuthUnifiedUser, 2)
            _login(user, force=True)
            with pytest.raises(AccountSuspendedError):
                app.view_functions["via_core"]()
