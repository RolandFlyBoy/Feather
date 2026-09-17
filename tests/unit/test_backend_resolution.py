"""Job, cache and storage backends chosen from what the environment provides.

An explicit JOB_BACKEND / CACHE_BACKEND / STORAGE_BACKEND always wins.
Otherwise REDIS_URL selects rq and redis, S3_BUCKET selects s3, then the
app's <KEY>_FALLBACK, then the framework defaults sync, memory and local.
"""

import itertools
import logging
import os

import pytest

from feather.core.config import AUTO_BACKENDS, config_lookup, resolve_backend

pytestmark = pytest.mark.unit

ENV_KEYS = (
    "JOB_BACKEND", "CACHE_BACKEND", "STORAGE_BACKEND", "REDIS_URL", "S3_BUCKET",
    "JOB_BACKEND_FALLBACK", "CACHE_BACKEND_FALLBACK", "STORAGE_BACKEND_FALLBACK",
    "FLASK_CONFIG", "FLASK_ENV",
)

REDIS = "redis://:pw@kv.internal:6379/0"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def lookup_from(values):
    return lambda key: values.get(key)


# =============================================================================
# resolve_backend: every combination
# =============================================================================

EXPECTED_DEFAULT = {"JOB_BACKEND": "sync", "CACHE_BACKEND": "memory", "STORAGE_BACKEND": "local"}
EXPECTED_SELECTED = {"JOB_BACKEND": "rq", "CACHE_BACKEND": "redis", "STORAGE_BACKEND": "s3"}
EXPLICIT = {"JOB_BACKEND": "thread", "CACHE_BACKEND": "memory", "STORAGE_BACKEND": "gcs"}
FALLBACK = {"JOB_BACKEND": "thread", "CACHE_BACKEND": "memory", "STORAGE_BACKEND": "gcs"}


@pytest.mark.parametrize(
    "key, explicit, trigger, fallback",
    [
        (key, explicit, trigger, fallback)
        for key in AUTO_BACKENDS
        for explicit, trigger, fallback in itertools.product((False, True), repeat=3)
    ],
)
def test_every_combination(key, explicit, trigger, fallback):
    trigger_key = AUTO_BACKENDS[key][0]
    values = {}
    if explicit:
        values[key] = EXPLICIT[key]
    if trigger:
        values[trigger_key] = REDIS if trigger_key == "REDIS_URL" else "bucket"
    if fallback:
        values[f"{key}_FALLBACK"] = FALLBACK[key]

    backend, reason = resolve_backend(key, lookup_from(values))

    if explicit:
        assert (backend, reason) == (EXPLICIT[key], f"{key} is set")
    elif trigger:
        assert (backend, reason) == (EXPECTED_SELECTED[key], f"{trigger_key} is set")
    elif fallback:
        assert (backend, reason) == (FALLBACK[key], f"{key}_FALLBACK")
    else:
        assert (backend, reason) == (EXPECTED_DEFAULT[key], "default")


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_values_count_as_unset(blank):
    values = {"JOB_BACKEND": blank, "REDIS_URL": REDIS}
    assert resolve_backend("JOB_BACKEND", lookup_from(values))[0] == "rq"
    values = {"JOB_BACKEND": None, "REDIS_URL": blank}
    assert resolve_backend("JOB_BACKEND", lookup_from(values))[0] == "sync"


def test_explicit_thread_with_redis_url_keeps_thread():
    values = {"JOB_BACKEND": "thread", "REDIS_URL": REDIS}
    assert resolve_backend("JOB_BACKEND", lookup_from(values))[0] == "thread"


def test_default_lookup_reads_the_environment(monkeypatch):
    monkeypatch.setenv("REDIS_URL", REDIS)
    monkeypatch.setenv("S3_BUCKET", "files")
    assert resolve_backend("JOB_BACKEND")[0] == "rq"
    assert resolve_backend("CACHE_BACKEND")[0] == "redis"
    assert resolve_backend("STORAGE_BACKEND")[0] == "s3"


def test_config_lookup_prefers_config_then_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", REDIS)
    lookup = config_lookup({"JOB_BACKEND": "thread", "CACHE_BACKEND": None})
    assert lookup("JOB_BACKEND") == "thread"
    assert lookup("CACHE_BACKEND") is None
    assert lookup("REDIS_URL") == REDIS


# =============================================================================
# The app resolves once, writes app.config and logs the result
# =============================================================================


class HardDefaultThreadConfig:
    """An existing app's config.py that hard-defaults its backends."""

    TESTING = True
    SECRET_KEY = "test"
    JOB_BACKEND = os.environ.get("JOB_BACKEND", "thread")
    CACHE_BACKEND = os.environ.get("CACHE_BACKEND", "memory")
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")


class UnsetConfig:
    """A newly scaffolded config.py: backends left to the framework."""

    TESTING = True
    SECRET_KEY = "test"
    JOB_BACKEND = None
    CACHE_BACKEND = None
    STORAGE_BACKEND = None
    JOB_BACKEND_FALLBACK = "thread"


def make_app(config_name, name="backend_resolution_app"):
    from feather import Feather

    return Feather(name, config_class=f"{__name__}.{config_name}")


class TestAppResolution:
    def test_platform_env_selects_rq_redis_and_s3(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", REDIS)
        monkeypatch.setenv("S3_BUCKET", "files")
        app = make_app("UnsetConfig")
        assert app.config["JOB_BACKEND"] == "rq"
        assert app.config["CACHE_BACKEND"] == "redis"
        assert app.config["STORAGE_BACKEND"] == "s3"

    def test_nothing_provided_uses_fallback_and_defaults(self):
        app = make_app("UnsetConfig")
        assert app.config["JOB_BACKEND"] == "thread"
        assert app.config["CACHE_BACKEND"] == "memory"
        assert app.config["STORAGE_BACKEND"] == "local"

    def test_hard_defaulted_config_keeps_its_backends(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", REDIS)
        monkeypatch.setenv("S3_BUCKET", "files")
        app = make_app("HardDefaultThreadConfig")
        assert app.config["JOB_BACKEND"] == "thread"
        assert app.config["CACHE_BACKEND"] == "memory"
        assert app.config["STORAGE_BACKEND"] == "local"

    def test_explicit_env_wins_over_redis_url(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", REDIS)
        monkeypatch.setenv("JOB_BACKEND", "sync")
        monkeypatch.setenv("CACHE_BACKEND", "memory")
        from feather import Feather

        app = Feather("builtin_config_app")
        assert app.config["JOB_BACKEND"] == "sync"
        assert app.config["CACHE_BACKEND"] == "memory"

    def test_builtin_config_leaves_backends_unset(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", REDIS)
        from feather import Feather

        app = Feather("builtin_config_app")
        assert app.config["JOB_BACKEND"] == "rq"
        assert app.config["CACHE_BACKEND"] == "redis"

    def test_backends_are_logged_once_at_info(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", REDIS)
        records = []

        class Collect(logging.Handler):
            def emit(self, record):
                records.append(record)

        name = "backend_log_app"
        handler = Collect(level=logging.DEBUG)
        logging.getLogger(name).addHandler(handler)
        try:
            make_app("UnsetConfig", name=name)
        finally:
            logging.getLogger(name).removeHandler(handler)

        lines = [r for r in records if r.getMessage().startswith("Backends:")]
        assert len(lines) == 1
        assert lines[0].levelno == logging.INFO
        assert lines[0].getMessage() == (
            "Backends: jobs=rq (REDIS_URL is set), cache=redis (REDIS_URL is set), "
            "storage=local (default)"
        )


# =============================================================================
# The backends themselves follow the resolution
# =============================================================================


class TestBackendsFollowResolution:
    def test_queue_and_cache_use_redis_url(self, monkeypatch):
        pytest.importorskip("rq")
        from feather.cache import get_cache
        from feather.cache.redis import RedisCache
        from feather.jobs import get_queue
        from feather.jobs.rq import RQQueue

        monkeypatch.setenv("REDIS_URL", REDIS)
        app = make_app("UnsetConfig")
        with app.app_context():
            queue = get_queue()
            cache = get_cache()
        assert isinstance(queue, RQQueue)
        assert isinstance(cache, RedisCache)
        kwargs = cache._client.connection_pool.connection_kwargs
        assert kwargs["host"] == "kv.internal"
        assert kwargs["password"] == "pw"

    def test_without_an_app_the_environment_decides(self, monkeypatch):
        pytest.importorskip("rq")
        from feather.core.registry import reset_backends
        from feather.jobs import _build_queue
        from feather.jobs.rq import RQQueue
        from feather.jobs.sync import SyncQueue

        assert isinstance(_build_queue(None), SyncQueue)
        monkeypatch.setenv("REDIS_URL", REDIS)
        assert isinstance(_build_queue(None), RQQueue)
        reset_backends(None)

    def test_security_check_treats_redis_url_as_rq(self):
        from feather.cli.security_check import Settings, check_job_serializer

        result = check_job_serializer(Settings("env", {"REDIS_URL": REDIS}))
        assert result.status == "WARN"
        result = check_job_serializer(
            Settings("env", {"REDIS_URL": REDIS, "JOB_BACKEND": "thread"})
        )
        assert result.status == "SKIP"


def test_env_check_does_not_require_unset_backends(tmp_path, monkeypatch):
    """The scaffold reads the backends with no fallback; unset is valid."""
    from click.testing import CliRunner

    from feather.cli.env import env_group

    (tmp_path / "config.py").write_text(
        "import os\n"
        "class Config:\n"
        "    JOB_BACKEND = os.environ.get('JOB_BACKEND')\n"
        "    CACHE_BACKEND = os.environ.get('CACHE_BACKEND')\n"
        "    STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND')\n"
    )
    (tmp_path / ".env").write_text("")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(env_group, ["check"])
    assert result.exit_code == 0, result.output
