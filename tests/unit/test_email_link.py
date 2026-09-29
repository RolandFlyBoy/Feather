"""How a sign-in code is sent and checked (feather/auth/email_link.py).

What must not regress: a code works only in the browser that asked for it and
only once; the session holds a keyed hash of it, never the code; wrong tries
run out, and replaying an old session cookie buys no more of them; and the
code never reaches a production log.
"""

import re
from unittest.mock import patch

import pytest
from flask import Flask, session

from feather.auth import email_link


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", SERVER_NAME="shop.example.com", APP_NAME="Petal & Stem")
    app.register_blueprint(email_link.email_auth_bp)
    email_link._here.clear()
    with app.app_context():
        yield app


@pytest.fixture(autouse=True)
def no_shared_cache():
    with patch("feather.cache.get_cache", side_effect=RuntimeError("no cache")):
        yield


def test_a_code_is_six_digits_and_leading_zeros_stay():
    codes = {email_link.new_code() for _ in range(200)}
    assert all(re.fullmatch(r"\d{6}", c) for c in codes)
    with patch("feather.auth.email_link.secrets.randbelow", return_value=42):
        assert email_link.new_code() == "000042"


def test_the_session_holds_a_hash_of_the_code_never_the_code(app):
    with app.test_request_context("/"):
        code = email_link.start(" A@B.co ")
        pending = session[email_link.PENDING_KEY]
        assert pending["e"] == "a@b.co" and code not in str(pending)
        assert email_link.check(code) == ("a@b.co", None)
        assert email_link.PENDING_KEY not in session


def test_a_code_works_once(app):
    with app.test_request_context("/"):
        code = email_link.start("a@b.co")
        replay = dict(session[email_link.PENDING_KEY])
        assert email_link.check(code)[0] == "a@b.co"
        session[email_link.PENDING_KEY] = replay  # the same cookie, sent again
        assert email_link.check(code) == (None, "expired")


def test_a_code_works_only_in_the_browser_that_asked_for_it(app):
    with app.test_request_context("/"):
        code = email_link.start("a@b.co")
    with app.test_request_context("/"):  # another browser: no pending sign-in
        assert email_link.check(code) == (None, "expired")


def test_wrong_tries_run_out_even_if_the_cookie_is_replayed(app):
    with app.test_request_context("/"):
        code = email_link.start("a@b.co")
        wrong = "000000" if code != "000000" else "111111"
        replay = dict(session[email_link.PENDING_KEY])
        for _ in range(email_link.MAX_ATTEMPTS - 1):
            assert email_link.check(wrong) == (None, "wrong")
        assert email_link.check(wrong) == (None, "attempts")
        session[email_link.PENDING_KEY] = replay
        assert email_link.check(code) == (None, "attempts")  # dead, right code or not


def test_asking_again_replaces_the_code(app):
    with app.test_request_context("/"):
        first = email_link.start("a@b.co")
        second = email_link.start("a@b.co")
        if first != second:
            assert email_link.check(first) == (None, "wrong")
        assert email_link.check(second)[0] == "a@b.co"


def test_a_code_expires(app):
    with app.test_request_context("/"):
        code = email_link.start("a@b.co")
        with patch("feather.auth.email_link.time.time", return_value=10**10):
            assert email_link.check(code) == (None, "expired")


def test_spaces_and_dashes_in_a_pasted_code_are_ignored(app):
    with app.test_request_context("/"):
        code = email_link.start("a@b.co")
        assert email_link.check(f" {code[:3]}-{code[3:]} ")[0] == "a@b.co"


def test_the_relay_is_told_only_the_address_the_code_and_the_apps_name(app):
    app.config.update(SIGN_IN_RELAY_URL="https://relay.example/sign-in", SIGN_IN_RELAY_TOKEN="t0k")
    with patch("feather.auth.email_link.requests.post") as post:
        post.return_value.status_code = 202
        assert email_link.send_code("a@b.co", "123456") is True
    args, kwargs = post.call_args
    assert args[0] == "https://relay.example/sign-in"
    assert kwargs["json"] == {"email": "a@b.co", "code": "123456", "app_name": "Petal & Stem", "minutes": 15}
    assert kwargs["headers"]["Authorization"] == "Bearer t0k"


def test_a_relay_that_refuses_means_no_email_was_sent(app):
    app.config.update(SIGN_IN_RELAY_URL="https://relay.example/sign-in", SIGN_IN_RELAY_TOKEN="t0k")
    with patch("feather.auth.email_link.requests.post") as post:
        post.return_value.status_code = 429
        assert email_link.send_code("a@b.co", "123456") is False


def test_with_nothing_configured_the_code_is_logged_only_in_development(app, caplog):
    app.debug = True
    with caplog.at_level("INFO"):
        assert email_link.send_code("a@b.co", "123456") is True
    assert "123456" in caplog.text


def test_in_production_an_unsendable_code_is_never_logged(app, caplog):
    app.debug = False
    app.testing = False
    with caplog.at_level("INFO"):
        assert email_link.send_code("a@b.co", "987654") is False
    assert "987654" not in caplog.text


def test_relay_settings_in_the_environment_are_used_when_config_omits_them(app, monkeypatch):
    # Found in a deployed app whose config.py class did not list them.
    monkeypatch.setenv("SIGN_IN_RELAY_URL", "https://relay.example/sign-in")
    monkeypatch.setenv("SIGN_IN_RELAY_TOKEN", "t0k")
    with patch("feather.auth.email_link.requests.post") as post:
        post.return_value.status_code = 202
        assert email_link.send_code("a@b.co", "123456") is True
    assert post.call_args.args[0] == "https://relay.example/sign-in"


def test_the_email_shows_the_code_centred_and_links_nowhere():
    body = email_link.code_email_html("042917", "Petal & Stem", 15)
    assert "042917" in body and "text-align:center" in body and "monospace" in body
    assert "<a " not in body and "href" not in body
