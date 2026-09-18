"""feather.testing.login_as: a test signs a user in and stays signed in.

Feather turns on Flask-Login's "strong" session protection, which signs out a
session whose identifier doesn't match the request. A session set by hand has
no identifier, so it looked signed in and then wasn't, and an app's tests had no
way to reach a signed-in page.
"""

from flask import Flask
from flask_login import UserMixin, current_user

from feather.auth.setup import login_manager
from feather.testing import login_as, logout


class _User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id


def _app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", TESTING=True)
    login_manager.init_app(app)
    login_manager.session_protection = "strong"
    login_manager.user_loader(lambda user_id: _User(user_id))

    @app.get("/who")
    def who():
        return current_user.get_id() if current_user.is_authenticated else "nobody"

    return app


def test_a_signed_in_user_stays_signed_in_across_requests():
    client = _app().test_client()
    assert client.get("/who").text == "nobody"

    login_as(client, _User("u1"))
    assert client.get("/who").text == "u1"
    assert client.get("/who").text == "u1"  # not signed out by session protection


def test_a_session_set_by_hand_is_what_strong_protection_signs_out():
    client = _app().test_client()
    with client.session_transaction() as session:
        session["_user_id"] = "u1"
        session["_fresh"] = True
    assert client.get("/who").text == "nobody"


def test_logout_signs_the_user_out():
    client = _app().test_client()
    login_as(client, _User("u1"))
    logout(client)
    assert client.get("/who").text == "nobody"


def test_the_csrf_aware_wrapper_works_too():
    class Wrapper:
        def __init__(self, flask_client):
            self._client = flask_client

    flask_client = _app().test_client()
    login_as(Wrapper(flask_client), _User("u2"))
    assert flask_client.get("/who").text == "u2"
