"""0.9.6 hardening: cache_response varies on the authenticated user and HX-Request."""

import pytest

import feather.cache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_cache_singleton():
    feather.cache._cache_instance = None
    yield
    feather.cache._cache_instance = None


class _User:
    """A flask_login-style user (has get_id, like UserMixin)."""

    is_authenticated = True

    def __init__(self, user_id):
        self.id = user_id

    def get_id(self):
        return str(self.id)


class _UserWithoutGetId:
    """A user object that only exposes .id - the key must still vary."""

    is_authenticated = True

    def __init__(self, user_id):
        self.id = user_id


class _Anonymous:
    is_authenticated = False
    id = None


@pytest.fixture
def fake_login(monkeypatch):
    """Make flask_login.current_user resolve to whatever the test sets."""
    state = {"user": _Anonymous()}
    monkeypatch.setattr("flask_login.utils._get_user", lambda: state["user"])
    return state


def _make_app(**kwargs):
    from tests.conftest import feather_app

    # TRUSTED_HOSTS None: the test client's Host header must not be rejected
    # if another test left TRUSTED_HOSTS in the environment.
    kwargs.setdefault("TRUSTED_HOSTS", None)
    return feather_app(CACHE_BACKEND="memory", **kwargs)


class TestVaryOnUser:
    def test_authenticated_users_do_not_share_cache_entries(self, fake_login):
        from feather.cache import cache_response
        from flask_login import current_user

        with _make_app() as app:
            @app.route("/me")
            @cache_response(ttl=60)
            def me():
                return {"user": current_user.id}

            client = app.test_client()

            fake_login["user"] = _User("alice")
            assert client.get("/me").get_json() == {"user": "alice"}

            fake_login["user"] = _User("bob")
            response = client.get("/me")
            assert response.get_json() == {"user": "bob"}
            assert response.headers.get("X-Cache") != "HIT"

            # Same user again is served from cache
            response = client.get("/me")
            assert response.get_json() == {"user": "bob"}
            assert response.headers.get("X-Cache") == "HIT"

    def test_anonymous_entries_are_not_served_to_authenticated_users(self, fake_login):
        from feather.cache import cache_response
        from flask_login import current_user

        with _make_app() as app:
            @app.route("/who")
            @cache_response(ttl=60)
            def who():
                return {"user": current_user.id if current_user.is_authenticated else None}

            client = app.test_client()
            assert client.get("/who").get_json() == {"user": None}

            fake_login["user"] = _User("alice")
            assert client.get("/who").get_json() == {"user": "alice"}

            fake_login["user"] = _Anonymous()
            response = client.get("/who")
            assert response.get_json() == {"user": None}
            assert response.headers.get("X-Cache") == "HIT"

    def test_user_object_without_get_id_still_varies(self, fake_login):
        from feather.cache import cache_response
        from flask_login import current_user

        with _make_app() as app:
            @app.route("/legacy")
            @cache_response(ttl=60)
            def legacy():
                return {"user": current_user.id}

            client = app.test_client()
            fake_login["user"] = _UserWithoutGetId("alice")
            assert client.get("/legacy").get_json() == {"user": "alice"}
            fake_login["user"] = _UserWithoutGetId("bob")
            assert client.get("/legacy").get_json() == {"user": "bob"}

    def test_explicit_vary_on_still_includes_user(self, fake_login):
        from feather.cache import cache_response
        from flask_login import current_user

        with _make_app() as app:
            @app.route("/search")
            @cache_response(ttl=60, vary_on=["query"])
            def search():
                return {"user": current_user.id}

            client = app.test_client()
            fake_login["user"] = _User("alice")
            assert client.get("/search?q=x").get_json() == {"user": "alice"}
            fake_login["user"] = _User("bob")
            assert client.get("/search?q=x").get_json() == {"user": "bob"}
            # Query variation is still respected
            assert client.get("/search?q=y").headers.get("X-Cache") != "HIT"

    def test_vary_on_user_false_shares_across_users(self, fake_login):
        from feather.cache import cache_response
        from flask_login import current_user

        with _make_app() as app:
            @app.route("/public")
            @cache_response(ttl=60, vary_on_user=False)
            def public():
                return {"user": current_user.id}

            client = app.test_client()
            fake_login["user"] = _User("alice")
            assert client.get("/public").get_json() == {"user": "alice"}
            fake_login["user"] = _User("bob")
            response = client.get("/public")
            assert response.get_json() == {"user": "alice"}
            assert response.headers.get("X-Cache") == "HIT"

    def test_works_without_flask_login_configured(self):
        """An app that never called init_auth must not crash on the default."""
        from feather.cache import cache_response

        calls = 0
        with _make_app() as app:
            # No login manager: flask_login.current_user raises on access
            app.login_manager = None
            if hasattr(app, "login_manager"):
                del app.login_manager

            @app.route("/plain")
            @cache_response(ttl=60)
            def plain():
                nonlocal calls
                calls += 1
                return {"ok": True}

            client = app.test_client()
            assert client.get("/plain").status_code == 200
            assert client.get("/plain").headers.get("X-Cache") == "HIT"
            assert calls == 1


class TestVaryOnHxRequest:
    def test_htmx_fragment_and_full_page_are_cached_separately(self):
        from feather.cache import cache_response
        from flask import request

        with _make_app() as app:
            @app.route("/page")
            @cache_response(ttl=60)
            def page():
                if request.headers.get("HX-Request"):
                    return "<div>fragment</div>"
                return "<html><body><div>fragment</div></body></html>"

            client = app.test_client()
            full = client.get("/page")
            assert full.get_data(as_text=True).startswith("<html>")

            partial = client.get("/page", headers={"HX-Request": "true"})
            assert partial.get_data(as_text=True) == "<div>fragment</div>"
            assert partial.headers.get("X-Cache") != "HIT"

            # Both variants are cached independently
            assert client.get("/page").get_data(as_text=True).startswith("<html>")
            assert client.get("/page").headers.get("X-Cache") == "HIT"
            again = client.get("/page", headers={"HX-Request": "true"})
            assert again.get_data(as_text=True) == "<div>fragment</div>"
            assert again.headers.get("X-Cache") == "HIT"
