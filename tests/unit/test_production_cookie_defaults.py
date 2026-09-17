"""A new app starts in production without hand-set cookie flags.

Found deploying a freshly scaffolded simple app: its ProductionConfig set no
cookie flags, so `feather start` refused to start (the security check failed
on SESSION_COOKIE_SECURE, REMEMBER_COOKIE_SECURE and REMEMBER_COOKIE_HTTPONLY),
and inside the image the .gitignore check failed too, because the generated
.dockerignore leaves .git and .gitignore out.
"""

from pathlib import Path

import pytest

from feather.cli.security_check import FAIL, PASS, SKIP, check_env_in_gitignore


class ProductionConfig:
    DEBUG = False
    SECRET_KEY = "x" * 64


class ProductionConfigWithOwnCookies(ProductionConfig):
    SESSION_COOKIE_SECURE = False


def _app(monkeypatch, config, env="production"):
    from feather.core.app import Feather

    if env:
        monkeypatch.setenv("FLASK_CONFIG", env)
    else:
        monkeypatch.delenv("FLASK_CONFIG", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    app = Feather.__new__(Feather)
    from flask import Flask

    Flask.__init__(app, "cookie_defaults_test")
    app.extensions["feather"] = {}
    app.config.from_object(config)
    app._secure_cookie_defaults(config)
    return app


def test_production_gets_secure_cookies(monkeypatch):
    app = _app(monkeypatch, ProductionConfig)
    for key, value in app.SECURE_COOKIE_DEFAULTS.items():
        assert app.config[key] == value


def test_the_apps_own_value_wins(monkeypatch):
    app = _app(monkeypatch, ProductionConfigWithOwnCookies)
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["REMEMBER_COOKIE_SECURE"] is True


def test_development_is_left_alone(monkeypatch):
    class DevelopmentConfig:
        DEBUG = True

    app = _app(monkeypatch, DevelopmentConfig, env="development")
    assert app.config["SESSION_COOKIE_SECURE"] is False


def test_the_gitignore_check_skips_outside_a_checkout(tmp_path: Path):
    assert check_env_in_gitignore(tmp_path).status == SKIP
    (tmp_path / ".git").mkdir()
    assert check_env_in_gitignore(tmp_path).status == FAIL
    (tmp_path / ".gitignore").write_text(".env\n")
    assert check_env_in_gitignore(tmp_path).status == PASS
