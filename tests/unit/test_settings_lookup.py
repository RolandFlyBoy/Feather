"""One config path for backend settings (0.9.8).

jobs and cache used to re-read os.environ with their own duplicated
fallbacks. They now go through feather.core.config.get_setting: the app
config first, the environment only when the app has no value (or there is
no app at all). No default value changed.
"""

import os
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def _app(**config):
    from feather import Feather

    app = Feather(__name__)
    app.config["TESTING"] = True
    for key, value in config.items():
        app.config[key] = value
    return app


class TestGetSetting:
    def test_reads_from_the_app_config_first(self):
        from feather.core.config import get_setting

        app = _app(JOB_BACKEND="thread")
        with app.app_context(), patch.dict(os.environ, {"JOB_BACKEND": "rq"}):
            assert get_setting("JOB_BACKEND", "sync") == "thread"

    def test_falls_back_to_the_environment_when_the_app_has_no_value(self):
        from feather.core.config import get_setting

        app = _app()
        with app.app_context():
            app.config.pop("FEATHER_MADE_UP_KEY", None)
            with patch.dict(os.environ, {"FEATHER_MADE_UP_KEY": "from-env"}):
                assert get_setting("FEATHER_MADE_UP_KEY", "fallback") == "from-env"

    def test_treats_a_none_config_value_as_unset(self):
        """config.py often writes KEY = os.environ.get('KEY'), leaving None."""
        from feather.core.config import get_setting

        app = _app(JOB_SERIALIZER=None)
        with app.app_context(), patch.dict(os.environ, {"JOB_SERIALIZER": "json"}):
            assert get_setting("JOB_SERIALIZER", "pickle") == "json"

    def test_uses_the_default_when_neither_has_a_value(self):
        from feather.core.config import get_setting

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEATHER_ANOTHER_MADE_UP_KEY", None)
            assert get_setting("FEATHER_ANOTHER_MADE_UP_KEY", "d") == "d"

    def test_works_without_an_app_context(self):
        from feather.core.config import get_setting

        with patch.dict(os.environ, {"FEATHER_NO_APP_KEY": "env-value"}):
            assert get_setting("FEATHER_NO_APP_KEY", "d") == "env-value"

    def test_cast_is_applied_to_environment_strings(self):
        from feather.core.config import get_setting

        with patch.dict(os.environ, {"JOB_MAX_WORKERS": "7"}):
            assert get_setting("JOB_MAX_WORKERS", 4, cast=int) == 7

    def test_bool_cast_understands_the_usual_spellings(self):
        from feather.core.config import get_setting, as_bool

        assert as_bool("true") is True
        assert as_bool("YES") is True
        assert as_bool("0") is False
        assert as_bool("") is False
        with patch.dict(os.environ, {"JOB_ENABLE_MONITORING": "yes"}):
            assert get_setting("JOB_ENABLE_MONITORING", False, cast=as_bool) is True


class TestDefaultsUnchanged:
    def test_job_defaults(self):
        from feather.core.registry import reset_backends
        from feather.jobs import get_queue
        from feather.jobs.sync import SyncQueue

        reset_backends(None, "queue")
        saved = {k: os.environ.pop(k, None) for k in ("JOB_BACKEND", "JOB_SERIALIZER")}
        try:
            assert isinstance(get_queue(), SyncQueue)
        finally:
            reset_backends(None, "queue")
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value

    def test_cache_defaults(self):
        from feather.cache.memory import MemoryCache
        from feather.cache import get_cache
        from feather.core.registry import reset_backends

        reset_backends(None, "cache")
        saved = {k: os.environ.pop(k, None) for k in ("CACHE_BACKEND", "CACHE_DEFAULT_TTL")}
        try:
            cache = get_cache()
            assert isinstance(cache, MemoryCache)
            assert cache._default_ttl == 300
        finally:
            reset_backends(None, "cache")
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value


class TestNoDuplicatedEnvReads:
    def test_jobs_module_no_longer_reads_os_environ_directly(self):
        source = (
            __import__("pathlib").Path(__import__("feather.jobs", fromlist=["x"]).__file__)
        ).read_text()
        assert "os.environ.get(" not in source

    def test_cache_module_no_longer_reads_os_environ_directly(self):
        source = (
            __import__("pathlib").Path(__import__("feather.cache", fromlist=["x"]).__file__)
        ).read_text()
        assert "os.environ.get(" not in source


class TestCastAppliesToStringConfigValues:
    def test_string_config_value_is_cast(self):
        from feather.core.config import get_setting

        app = _app(JOB_MAX_WORKERS="8")
        with app.app_context():
            assert get_setting("JOB_MAX_WORKERS", 4, cast=int) == 8

    def test_typed_config_value_is_left_alone(self):
        from feather.core.config import get_setting

        app = _app(JOB_MAX_WORKERS=6)
        with app.app_context():
            assert get_setting("JOB_MAX_WORKERS", 4, cast=int) == 6

    def test_unparseable_value_falls_back_to_the_default(self):
        from feather.core.config import get_setting

        app = _app(JOB_MAX_WORKERS="not-a-number")
        with app.app_context():
            assert get_setting("JOB_MAX_WORKERS", 4, cast=int) == 4
