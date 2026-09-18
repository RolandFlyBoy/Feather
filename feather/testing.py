"""Helpers for an app's own tests.

A generated app's ``tests/conftest.py`` uses these; nothing here runs outside a
test.
"""

from __future__ import annotations


def login_as(client, user, *, fresh: bool = True):
    """Sign ``user`` in on a Flask test client, and return the client.

    Feather protects sessions with Flask-Login's "strong" mode, which logs out
    any session whose identifier does not match the request's address and
    browser. Setting ``_user_id`` on a test client's session by hand therefore
    looks like it works and then silently signs the user out on the next
    request. This sets the identifier the client's own requests will produce.

    ``client`` may be the plain test client or the CSRF-aware wrapper from
    ``tests/conftest.py``; ``user`` is any model with ``get_id()``.

        def test_dashboard(client, user):
            login_as(client, user)
            assert client.get("/dashboard").status_code == 200
    """
    from feather.auth.setup import login_manager

    flask_client = getattr(client, "_client", None) or getattr(client, "client", None) or client
    app = flask_client.application
    with app.test_request_context(environ_base=dict(flask_client.environ_base)):
        identifier = login_manager._session_identifier_generator()
    with flask_client.session_transaction() as session:
        session["_user_id"] = str(user.get_id())
        session["_fresh"] = fresh
        session["_id"] = identifier
    return client


def logout(client):
    """Sign whoever is signed in on ``client`` out again."""
    flask_client = getattr(client, "_client", None) or getattr(client, "client", None) or client
    with flask_client.session_transaction() as session:
        for key in ("_user_id", "_fresh", "_id", "_remember"):
            session.pop(key, None)
    return client
