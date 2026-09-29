"""Logout is POST only.

GET /auth/logout would be logout CSRF: any page could log a user out with an
<img> tag.
"""

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

    def test_route_accepts_only_post(self, app):
        methods = set()
        for rule in app.url_map.iter_rules():
            if rule.rule == "/auth/logout":
                methods = rule.methods
        assert "POST" in methods
        assert "GET" not in methods

    def test_get_does_not_log_out(self, app):
        client = _logged_in_client(app)
        assert client.get("/auth/logout").status_code == 405
