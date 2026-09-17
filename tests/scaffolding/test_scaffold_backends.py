"""Scaffolded backends: unset in config.py, chosen by the framework.

The generated config.py leaves JOB_BACKEND, CACHE_BACKEND and
STORAGE_BACKEND unset so REDIS_URL and S3_BUCKET can select a backend on a
platform that injects them. Local development must behave exactly as before,
so the generated .env keeps its explicit dev values.
"""

import importlib.util
import os

import pytest

from feather.cli._docker_templates import render_env_example
from feather.core.config import AUTO_BACKENDS, resolve_backend
from feather.scaffold import render_project
from tests.scaffolding.test_scaffold_overlays import OPTION_SETS

pytestmark = pytest.mark.scaffolding

REDIS = "redis://:pw@kv.internal:6379/0"
ENV_KEYS = tuple(AUTO_BACKENDS) + ("REDIS_URL", "S3_BUCKET", "FLASK_ENV", "JOB_SERIALIZER")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def parse_env(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.split("#", 1)[0].strip()
    return values


def resolved(files, tmp_path, monkeypatch, env):
    """Import the generated config.py under ``env`` and resolve the backends."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    path = tmp_path / "config.py"
    path.write_text(files["config.py"])
    spec = importlib.util.spec_from_file_location("scaffolded_config_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = module.DevelopmentConfig

    def lookup(key):
        value = getattr(config, key, None)
        if value not in (None, ""):
            return value
        raw = os.environ.get(key)
        return raw or None

    return {key: resolve_backend(key, lookup)[0] for key in AUTO_BACKENDS}


@pytest.mark.parametrize("shape", sorted(OPTION_SETS))
def test_config_never_hard_defaults_a_backend(shape):
    config = render_project(OPTION_SETS[shape])["config.py"]
    for key in AUTO_BACKENDS:
        assert f'os.environ.get("{key}", ' not in config
        if f"{key} =" in config:
            assert f'{key} = os.environ.get("{key}")' in config


@pytest.mark.parametrize(
    "shape, expected",
    [
        ("simple", {"JOB_BACKEND": "sync", "CACHE_BACKEND": "memory", "STORAGE_BACKEND": "local"}),
        ("everything", {"JOB_BACKEND": "thread", "CACHE_BACKEND": "redis", "STORAGE_BACKEND": "gcs"}),
        ("features_without_auth",
         {"JOB_BACKEND": "thread", "CACHE_BACKEND": "redis", "STORAGE_BACKEND": "gcs"}),
    ],
)
def test_development_with_the_generated_env_is_unchanged(shape, expected, tmp_path, monkeypatch):
    """Same backends 0.9.14 gave these apps with their own .env."""
    files = render_project(OPTION_SETS[shape])
    env = {k: v for k, v in parse_env(files[".env"]).items() if v}
    assert resolved(files, tmp_path, monkeypatch, env) == expected


def test_jobs_app_without_redis_keeps_the_thread_pool(tmp_path, monkeypatch):
    files = render_project(OPTION_SETS["features_without_auth"])
    assert resolved(files, tmp_path, monkeypatch, {})["JOB_BACKEND"] == "thread"


@pytest.mark.parametrize("shape", sorted(OPTION_SETS))
def test_platform_env_selects_redis_and_s3(shape, tmp_path, monkeypatch):
    files = render_project(OPTION_SETS[shape])
    backends = resolved(files, tmp_path, monkeypatch, {"REDIS_URL": REDIS, "S3_BUCKET": "files"})
    assert backends == {"JOB_BACKEND": "rq", "CACHE_BACKEND": "redis", "STORAGE_BACKEND": "s3"}


def test_production_guard_warns_for_rq_selected_by_redis_url(tmp_path, monkeypatch, caplog):
    """JOB_BACKEND is unset, but REDIS_URL makes it rq, so the guard applies."""
    files = render_project(OPTION_SETS["features_without_auth"])
    monkeypatch.setenv("REDIS_URL", "redis://kv.internal:6379/0")
    (tmp_path / "config.py").write_text(files["config.py"])
    spec = importlib.util.spec_from_file_location("guard_config", tmp_path / "config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with caplog.at_level("WARNING"):
        module.ProductionConfig.check_job_backend()
    assert "no password" in caplog.text


def test_storage_env_lists_s3_keys_commented():
    files = render_project(OPTION_SETS["everything"])
    env = files[".env"]
    for key in ("S3_BUCKET", "S3_ENDPOINT", "S3_REGION", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        assert f"# {key}=\n" in env
    assert "S3_BUCKET" not in parse_env(env)
    example = render_env_example("full_app", base_env=env)
    assert "# S3_SECRET_ACCESS_KEY=\n" in example


@pytest.mark.parametrize("shape", sorted(OPTION_SETS))
def test_readme_has_a_deploy_section(shape):
    readme = render_project(OPTION_SETS[shape])["README.md"]
    assert "## Deploy" in readme
    assert "https://docs.featherframework.org/deployment/docker" in readme
    assert "https://app.appentic.com/deploy?repo=https://github.com/OWNER/REPO" in readme
    assert "Replace `OWNER/REPO`" in readme
