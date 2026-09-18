"""How a sign-in link is sent and checked (feather/auth/email_link.py)."""

from unittest.mock import patch

import pytest
from flask import Flask

from feather.auth import email_link


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", SERVER_NAME="shop.example.com", APP_NAME="Petal & Stem")
    app.register_blueprint(email_link.email_auth_bp)
    with app.app_context():
        yield app


def test_the_relay_is_told_only_the_address_the_link_and_the_apps_name(app):
    app.config.update(SIGN_IN_RELAY_URL="https://relay.example/sign-in", SIGN_IN_RELAY_TOKEN="t0k")
    with patch("feather.auth.email_link.requests.post") as post:
        post.return_value.status_code = 202
        assert email_link.send_link("a@b.co", "https://shop.example.com/x") is True
    args, kwargs = post.call_args
    assert args[0] == "https://relay.example/sign-in"
    assert kwargs["json"] == {"email": "a@b.co", "link": "https://shop.example.com/x", "app_name": "Petal & Stem"}
    assert kwargs["headers"]["Authorization"] == "Bearer t0k"


def test_a_relay_that_refuses_means_no_email_was_sent(app):
    app.config.update(SIGN_IN_RELAY_URL="https://relay.example/sign-in", SIGN_IN_RELAY_TOKEN="t0k")
    with patch("feather.auth.email_link.requests.post") as post:
        post.return_value.status_code = 429
        assert email_link.send_link("a@b.co", "https://shop.example.com/x") is False


def test_with_nothing_configured_the_link_is_logged(app, caplog):
    with caplog.at_level("INFO"):
        assert email_link.send_link("a@b.co", "https://shop.example.com/x") is True
    assert "https://shop.example.com/x" in caplog.text


def test_a_link_is_genuine_in_date_and_names_its_address(app):
    link = email_link.make_link(" A@B.co ")
    token = link.split("token=", 1)[1]
    assert link.startswith("http://shop.example.com/auth/email/verify")
    assert email_link.read_token(token)["e"] == "a@b.co"
    assert email_link.read_token(token + "x") is None
    app.config["SIGN_IN_LINK_MINUTES"] = 0
    with patch("itsdangerous.timed.time.time", return_value=10**10):
        assert email_link.read_token(token) is None  # expired


def test_a_link_is_used_once(app):
    email_link._used_here.clear()
    with patch("feather.cache.get_cache", side_effect=RuntimeError("no cache")):
        assert email_link._mark_used("n1") is True
        assert email_link._mark_used("n1") is False
