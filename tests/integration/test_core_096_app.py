"""Regression tests for 0.9.6 app-level hardening.

Covers TRUSTED_HOSTS, the ProxyFix toggle and the CSRF token lifetime default.
"""

import os
from contextlib import contextmanager

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

pytestmark = pytest.mark.integration


@contextmanager
def env(**values):
    saved = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def make_app():
    from feather import Feather

    app = Feather(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    return app


# =============================================================================
# TRUSTED_HOSTS
# =============================================================================


class TestTrustedHosts:
    def test_trusted_hosts_from_env_is_parsed_into_a_list(self):
        with env(TRUSTED_HOSTS="good.example.com, other.example.com"):
            app = make_app()

        assert app.config["TRUSTED_HOSTS"] == ["good.example.com", "other.example.com"]

    def test_default_is_none(self):
        with env(TRUSTED_HOSTS=None):
            app = make_app()

        assert app.config["TRUSTED_HOSTS"] is None

    def test_foreign_host_header_is_rejected(self):
        with env(TRUSTED_HOSTS="good.example.com"):
            app = make_app()

        client = app.test_client()
        response = client.get("/health", headers={"Host": "evil.example.com"})
        assert response.status_code == 400

    def test_trusted_host_header_is_accepted(self):
        with env(TRUSTED_HOSTS="good.example.com"):
            app = make_app()

        client = app.test_client()
        response = client.get("/health", headers={"Host": "good.example.com"})
        assert response.status_code != 400

    def test_config_list_is_honoured(self):
        from feather import Feather

        class HostConfig:
            TESTING = True
            SECRET_KEY = "test-secret"
            TRUSTED_HOSTS = ["configured.example.com"]

        with env(TRUSTED_HOSTS=None):
            app = Feather(__name__)
            app.config.from_object(HostConfig)

        assert app.config["TRUSTED_HOSTS"] == ["configured.example.com"]


# =============================================================================
# ProxyFix toggle
# =============================================================================


class TestProxyFixToggle:
    def test_enabled_by_default(self):
        with env(FEATHER_PROXY_FIX=None):
            app = make_app()

        assert isinstance(app.wsgi_app, ProxyFix)

    def test_can_be_disabled_via_env(self):
        with env(FEATHER_PROXY_FIX="false"):
            app = make_app()

        assert not isinstance(app.wsgi_app, ProxyFix)

    def test_hop_count_is_configurable(self):
        with env(FEATHER_PROXY_FIX_NUM="2"):
            app = make_app()

        assert isinstance(app.wsgi_app, ProxyFix)
        assert app.wsgi_app.x_for == 2
        assert app.wsgi_app.x_proto == 2
        assert app.wsgi_app.x_host == 2

    def test_default_hop_count_is_one(self):
        with env(FEATHER_PROXY_FIX_NUM=None):
            app = make_app()

        assert app.wsgi_app.x_for == 1


# =============================================================================
# CSRF token lifetime
# =============================================================================


class TestCsrfTimeLimitDefault:
    def test_project_config_without_the_key_gets_none(self):
        """A project config.py that doesn't subclass feather's Config."""
        from feather import Feather

        class PlainConfig:
            TESTING = True
            SECRET_KEY = "test-secret"

        app = Feather(__name__)
        app.config.from_object(PlainConfig)

        # The framework default must already be in place after init.
        assert app.config["WTF_CSRF_TIME_LIMIT"] is None
