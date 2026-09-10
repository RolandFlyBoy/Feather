"""Logout is POST-first, GET deprecated (0.9.8).

GET /auth/logout is logout CSRF: any page can log a user out with an
<img> tag. The scaffold already POSTs. GET keeps working for one more
release but emits a DeprecationWarning and a log line.
"""

import warnings

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

pytestmark = pytest.mark.unit


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config["SECRET_KEY"] = "test-secret"
    application.config["WTF_CSRF_ENABLED"] = False

    login_manager = LoginManager()
    login_manager.init_app(application)

    class MockUser(UserMixin):
        id = "1"

    @login_manager.user_loader
    def load_user(user_id):
        return MockUser()

    from feather.auth.routes import auth_bp

    application.register_blueprint(auth_bp)

    def home():
        return "home"

    application.add_url_rule("/", "page.home", home)
    return application


def _logged_in_client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
    return client


class TestPost:
    def test_post_logs_out(self, app):
        client = _logged_in_client(app)
        response = client.post("/auth/logout")
        assert response.status_code == 302
        assert response.location == "/"

    def test_post_does_not_warn(self, app):
        client = _logged_in_client(app)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.post("/auth/logout")
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []

    def test_route_accepts_both_methods(self, app):
        methods = set()
        for rule in app.url_map.iter_rules():
            if rule.rule == "/auth/logout":
                methods = rule.methods
        assert "POST" in methods
        assert "GET" in methods


class TestGetDeprecated:
    def test_get_still_logs_out(self, app):
        client = _logged_in_client(app)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            response = client.get("/auth/logout")
        assert response.status_code == 302
        assert response.location == "/"

    def test_get_emits_a_deprecation_warning(self, app):
        client = _logged_in_client(app)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.get("/auth/logout")
        deprecations = [
            str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert deprecations, "GET /auth/logout must warn"
        assert "POST" in deprecations[0]

    def test_get_logs_a_line(self, app, caplog):
        client = _logged_in_client(app)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with caplog.at_level("WARNING"):
                client.get("/auth/logout")
        assert any("logout" in record.message.lower() for record in caplog.records)
