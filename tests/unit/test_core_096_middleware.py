"""Regression tests for 0.9.6 middleware fixes.

Covers request id validation and the duplicated log handler.
"""

import logging

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def middleware_app():
    from feather import Feather

    app = Feather(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    @app.route("/ping")
    def ping():
        return {"ok": True}

    return app


class TestRequestIdValidation:
    def test_valid_request_id_is_preserved(self, middleware_app):
        client = middleware_app.test_client()
        response = client.get("/ping", headers={"X-Request-ID": "abc-123_XY.9"})

        assert response.headers["X-Request-ID"] == "abc-123_XY.9"

    @pytest.mark.parametrize(
        "bad_id",
        [
            "has spaces",
            "id\twith\ttabs",
            "<script>alert(1)</script>",
            "a" * 129,
            "",
        ],
    )
    def test_invalid_request_id_is_regenerated(self, middleware_app, bad_id):
        client = middleware_app.test_client()
        response = client.get("/ping", headers={"X-Request-ID": bad_id})

        returned = response.headers["X-Request-ID"]
        assert returned != bad_id
        assert len(returned) == 36  # a fresh uuid4

    def test_is_valid_request_id_helper(self):
        from feather.core.middleware import _is_valid_request_id

        assert _is_valid_request_id("abc-123")
        assert _is_valid_request_id("a" * 128)
        assert not _is_valid_request_id("a" * 129)
        assert not _is_valid_request_id("bad id")
        assert not _is_valid_request_id("inject\r\nHeader: x")
        assert not _is_valid_request_id(None)


class TestLoggingHandlers:
    def test_flask_default_handler_is_removed(self, middleware_app):
        """setup_logging must not leave Flask's handler on app.logger."""
        from flask.logging import default_handler

        assert default_handler not in middleware_app.logger.handlers

    def test_setup_logging_strips_the_default_handler(self):
        """Explicitly: a Flask app logging through its own handler is fixed.

        Flask attaches its default handler to app.logger; the framework's
        handlers live on the root logger, so every line would be emitted twice.
        """
        import logging

        from flask import Flask
        from flask.logging import default_handler

        from feather.core.middleware import setup_logging

        app = Flask(__name__)
        app.logger.addHandler(default_handler)
        assert default_handler in app.logger.handlers

        root_handlers = list(logging.getLogger().handlers)
        try:
            setup_logging(app)
            assert default_handler not in app.logger.handlers
            # Records still reach the framework handlers via propagation.
            assert app.logger.propagate is True
        finally:
            logging.getLogger().handlers = root_handlers
