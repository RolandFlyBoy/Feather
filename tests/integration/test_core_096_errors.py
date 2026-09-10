"""Regression tests for 0.9.6 error handling.

Covers:
- meta.request_id reusing the middleware's request id.
- Plain werkzeug HTTPExceptions (403, 405, CSRF 400) returning the standard
  JSON envelope on API requests.
"""

import pytest
from flask import abort

from tests.conftest import make_csrf_client

pytestmark = pytest.mark.integration


@pytest.fixture
def api_error_app():
    from feather import Feather
    from feather.db import db
    from feather.exceptions import ValidationError

    app = Feather(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/api/forbidden")
    def forbidden():
        abort(403)

    @app.route("/api/gone")
    def gone():
        abort(410)

    @app.route("/api/get-only", methods=["GET"])
    def get_only():
        return {"ok": True}

    @app.route("/api/needs-csrf", methods=["POST"])
    def needs_csrf():
        return {"ok": True}

    @app.route("/api/validation")
    def validation():
        raise ValidationError("bad input", field="name")

    @app.route("/api/boom")
    def boom():
        raise RuntimeError("kaboom")

    @app.route("/page/forbidden")
    def page_forbidden():
        abort(403)

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def assert_envelope(payload):
    assert payload["success"] is False
    assert payload["data"] is None
    assert isinstance(payload["error"], dict)
    assert isinstance(payload["error"]["code"], str)
    assert isinstance(payload["error"]["message"], str)
    assert "timestamp" in payload["meta"]


# =============================================================================
# request_id reuse
# =============================================================================


class TestRequestIdReuse:
    def test_feather_exception_reuses_request_id(self, api_error_app):
        client = api_error_app.test_client()
        response = client.get("/api/validation", headers={"X-Request-ID": "abc-123"})

        assert response.headers["X-Request-ID"] == "abc-123"
        assert response.get_json()["meta"]["request_id"] == "abc-123"

    def test_server_error_reuses_request_id(self, api_error_app):
        client = api_error_app.test_client()
        response = client.get("/api/boom", headers={"X-Request-ID": "abc-456"})

        assert response.status_code == 500
        assert response.get_json()["meta"]["request_id"] == "abc-456"

    def test_generated_request_id_matches_header(self, api_error_app):
        client = api_error_app.test_client()
        response = client.get("/api/validation")

        assert response.get_json()["meta"]["request_id"] == response.headers["X-Request-ID"]


# =============================================================================
# Plain HTTPExceptions on API routes
# =============================================================================


class TestHttpExceptionJson:
    def test_abort_403_returns_json(self, api_error_app):
        client = api_error_app.test_client()
        response = client.get("/api/forbidden")

        assert response.status_code == 403
        assert response.content_type.startswith("application/json")
        payload = response.get_json()
        assert_envelope(payload)
        assert payload["error"]["code"] == "FORBIDDEN"

    def test_method_not_allowed_returns_json(self, api_error_app):
        client = make_csrf_client(api_error_app)
        response = client.post("/api/get-only", json={})

        assert response.status_code == 405
        payload = response.get_json()
        assert_envelope(payload)
        assert payload["error"]["code"] == "METHOD_NOT_ALLOWED"

    def test_csrf_failure_returns_json(self, api_error_app):
        client = api_error_app.test_client()
        response = client.post("/api/needs-csrf", json={})

        assert response.status_code == 400
        payload = response.get_json()
        assert_envelope(payload)
        assert payload["error"]["code"] == "CSRF_ERROR"

    def test_uncommon_status_still_json(self, api_error_app):
        client = api_error_app.test_client()
        response = client.get("/api/gone")

        assert response.status_code == 410
        assert_envelope(response.get_json())

    def test_json_accept_header_gets_json(self, api_error_app):
        """Non-/api paths still get JSON when the client asks for it."""
        client = api_error_app.test_client()
        response = client.get("/page/forbidden", headers={"Accept": "application/json"})

        assert response.status_code == 403
        assert_envelope(response.get_json())

    def test_html_client_still_gets_html(self, api_error_app):
        """Browsers keep the HTML error page."""
        client = api_error_app.test_client()
        response = client.get("/page/forbidden", headers={"Accept": "text/html"})

        assert response.status_code == 403
        assert not response.content_type.startswith("application/json")

    def test_404_uses_the_shared_api_detection(self, api_error_app):
        """A JSON client hitting an unknown non-/api path gets JSON."""
        client = api_error_app.test_client()
        response = client.get("/nope", headers={"Accept": "application/json"})

        assert response.status_code == 404
        payload = response.get_json()
        assert_envelope(payload)
        assert payload["error"]["code"] == "NOT_FOUND"

    def test_api_404_unchanged(self, api_error_app):
        client = api_error_app.test_client()
        response = client.get("/api/missing")

        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "NOT_FOUND"
