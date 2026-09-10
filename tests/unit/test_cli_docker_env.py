"""Unit tests for `feather docker init`, `feather env check` and the pieces
they share: the Docker file bodies and the `.feather-templates` link.
"""

import os
import stat

import pytest
from click.testing import CliRunner

from feather.cli._docker_templates import (
    HEALTH_PATH,
    docker_files,
    render_env_example,
    slugify,
    write_docker_files,
)
from feather.cli._templates_link import LINK_NAME, ensure_templates_link, feather_templates_dir
from feather.cli.docker import detect_features, docker
from feather.cli.env import collect_env_refs, env_group

pytestmark = pytest.mark.unit


def _code_lines(text: str) -> str:
    """Drop comment and blank lines, so assertions do not match prose."""
    return "\n".join(
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


ALL_FILES = {
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    "docker-compose.dev.yml",
    "deploy/Caddyfile",
    "deploy/deploy.sh",
    "deploy/backup.sh",
    ".env.example",
}


@pytest.fixture
def project(tmp_path):
    """A directory that looks enough like a Feather project."""
    (tmp_path / "app.py").write_text("from feather import Feather\napp = Feather(__name__)\n")
    (tmp_path / ".env").write_text("SECRET_KEY=dev\nDATABASE_URL=postgresql://localhost/x\n")
    return tmp_path


# =============================================================================
# slugify
# =============================================================================


class TestSlugify:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("MyApp", "myapp"),
            ("my-app", "my_app"),
            ("My App 2", "my_app_2"),
            ("2fast", "app_2fast"),
            ("", "app"),
            ("--", "app"),
        ],
    )
    def test_slug(self, raw, expected):
        assert slugify(raw) == expected


# =============================================================================
# feather docker init
# =============================================================================


class TestDockerInit:
    def test_refuses_outside_a_project(self, tmp_path):
        result = CliRunner().invoke(docker, ["init", "--path", str(tmp_path)])
        assert result.exit_code != 0
        assert "Not in a Feather project" in result.output

    def test_writes_every_file(self, project):
        result = CliRunner().invoke(docker, ["init", "--path", str(project)])
        assert result.exit_code == 0, result.output
        for name in ALL_FILES:
            assert (project / name).exists(), f"{name} not written"
        assert "written" in result.output

    def test_scripts_are_executable(self, project):
        CliRunner().invoke(docker, ["init", "--path", str(project)])
        for script in ("deploy/deploy.sh", "deploy/backup.sh"):
            assert (project / script).stat().st_mode & stat.S_IXUSR

    def test_second_run_skips_everything(self, project):
        CliRunner().invoke(docker, ["init", "--path", str(project)])
        (project / "Dockerfile").write_text("# hand edited\n")

        result = CliRunner().invoke(docker, ["init", "--path", str(project)])
        assert result.exit_code == 0, result.output
        assert (project / "Dockerfile").read_text() == "# hand edited\n"
        assert "skipped" in result.output
        assert "--force" in result.output

    def test_force_overwrites(self, project):
        CliRunner().invoke(docker, ["init", "--path", str(project)])
        (project / "Dockerfile").write_text("# hand edited\n")

        result = CliRunner().invoke(docker, ["init", "--path", str(project), "--force"])
        assert result.exit_code == 0, result.output
        assert (project / "Dockerfile").read_text() != "# hand edited\n"
        assert "overwritten" in result.output

    def test_force_only_touches_its_own_files(self, project):
        CliRunner().invoke(docker, ["init", "--path", str(project)])
        (project / "app.py").write_text("# mine\n")
        CliRunner().invoke(docker, ["init", "--path", str(project), "--force"])
        assert (project / "app.py").read_text() == "# mine\n"

    def test_no_worker_flag_drops_the_worker(self, project):
        (project / "worker.py").write_text("")  # would otherwise be detected
        CliRunner().invoke(docker, ["init", "--path", str(project), "--no-worker"])
        assert "AS worker" not in (project / "Dockerfile").read_text()
        assert "target: worker" not in (project / "docker-compose.yml").read_text()

    def test_worker_flag_forces_the_worker(self, project):
        CliRunner().invoke(docker, ["init", "--path", str(project), "--worker"])
        assert "AS worker" in (project / "Dockerfile").read_text()
        assert "target: worker" in (project / "docker-compose.yml").read_text()

    def test_domain_lands_in_env_example(self, project):
        CliRunner().invoke(
            docker, ["init", "--path", str(project), "--domain", "app.example.com"]
        )
        assert "DOMAIN=app.example.com" in (project / ".env.example").read_text()

    def test_name_option_sets_the_compose_project(self, project):
        CliRunner().invoke(docker, ["init", "--path", str(project), "--name", "My App"])
        compose = (project / "docker-compose.yml").read_text()
        assert "name: my_app" in compose
        assert "POSTGRES_DB: my_app" in compose

    def test_existing_env_seeds_the_example(self, project):
        (project / ".env").write_text("SECRET_KEY=hunter2\nMY_OWN_SETTING=visible\n")
        CliRunner().invoke(docker, ["init", "--path", str(project)])
        example = (project / ".env.example").read_text()
        assert "MY_OWN_SETTING=visible" in example
        assert "hunter2" not in example
        assert "SECRET_KEY=\n" in example

    def test_health_path_is_reported(self, project):
        result = CliRunner().invoke(docker, ["init", "--path", str(project)])
        assert HEALTH_PATH in result.output


class TestDetectFeatures:
    def test_database_from_env(self, tmp_path):
        (tmp_path / ".env").write_text("DATABASE_URL=postgresql://localhost/x\n")
        assert detect_features(tmp_path)["database"] is True

    def test_no_database(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET_KEY=x\n")
        features = detect_features(tmp_path)
        assert features["database"] is False
        assert features["worker"] is False

    def test_worker_from_job_backend(self, tmp_path):
        (tmp_path / ".env").write_text("JOB_BACKEND=rq\n")
        features = detect_features(tmp_path)
        assert features["worker"] is True
        # A worker without Redis behind it is useless.
        assert features["redis"] is True

    def test_worker_from_worker_py(self, tmp_path):
        (tmp_path / "worker.py").write_text("")
        assert detect_features(tmp_path)["worker"] is True

    def test_redis_from_config(self, tmp_path):
        (tmp_path / "config.py").write_text('CACHE_URL = "redis://localhost:6379/0"\n')
        assert detect_features(tmp_path)["redis"] is True

    def test_database_from_models_directory(self, tmp_path):
        (tmp_path / "models").mkdir()
        assert detect_features(tmp_path)["database"] is True


# =============================================================================
# The file bodies
# =============================================================================


class TestDockerFileBodies:
    def test_every_file_is_produced(self):
        names = {f.path for f in docker_files("demo")}
        assert names == ALL_FILES

    def test_only_the_scripts_are_executable(self):
        executables = {f.path for f in docker_files("demo") if f.executable}
        assert executables == {"deploy/deploy.sh", "deploy/backup.sh"}

    def test_no_render_references(self):
        for item in docker_files("demo"):
            assert "render.com" not in item.content.lower()
            assert "onrender" not in item.content.lower()

    def test_placeholders_are_all_substituted(self):
        for item in docker_files("demo", app_slug="demo"):
            for placeholder in ("{app_name}", "{app_slug}", "{health_path}", "{port}"):
                assert placeholder not in item.content, f"{placeholder} left in {item.path}"

    def test_compose_literal_braces_survive(self):
        compose = next(f for f in docker_files("demo") if f.path == "docker-compose.yml")
        assert "${POSTGRES_PASSWORD" in compose.content
        caddy = next(f for f in docker_files("demo") if f.path == "deploy/Caddyfile")
        assert "{$DOMAIN}" in caddy.content
        assert "{remote_host}" in caddy.content
        script = next(f for f in docker_files("demo") if f.path == "deploy/deploy.sh")
        assert "{{.State.Health.Status}}" in script.content

    def test_no_migrations_in_the_container_command(self):
        # Two web containers starting at once would race on `db upgrade`.
        dockerfile = next(f for f in docker_files("demo") if f.path == "Dockerfile")
        cmds = [line for line in dockerfile.content.splitlines() if line.startswith("CMD")]
        assert cmds and all("db upgrade" not in line for line in cmds)
        # It happens exactly once, in the deploy script.
        deploy = next(f for f in docker_files("demo") if f.path == "deploy/deploy.sh")
        assert "docker compose run --rm web feather db upgrade" in deploy.content

    def test_without_database_there_is_no_db_service_or_migration(self):
        files = {f.path: f.content for f in docker_files("demo", database=False)}
        assert "image: postgres" not in files["docker-compose.yml"]
        assert "docker compose run --rm web feather db upgrade" not in files["deploy/deploy.sh"]
        assert "pg_dump" not in _code_lines(files["deploy/backup.sh"])

    def test_without_redis_there_is_no_redis_service(self):
        files = {f.path: f.content for f in docker_files("demo", redis=False, worker=False)}
        assert "valkey" not in files["docker-compose.yml"]
        assert "REDIS_URL" not in files["docker-compose.yml"]


class TestEnvExampleRendering:
    def test_marks_compose_provided_keys(self):
        body = render_env_example("demo", base_env="DATABASE_URL=x\nSECRET_KEY=y\n")
        assert "# DATABASE_URL=   # supplied by docker-compose.yml" in body
        assert "SECRET_KEY=\n" in body

    def test_falls_back_without_a_base_env(self):
        body = render_env_example("demo", base_env=None)
        assert "SECRET_KEY=" in body

    def test_keeps_non_secret_values(self):
        body = render_env_example("demo", base_env="JOB_MAX_WORKERS=2\n")
        assert "JOB_MAX_WORKERS=2" in body


class TestWriteDockerFiles:
    def test_reports_written_then_skipped(self, tmp_path):
        files = docker_files("demo")
        first = dict(write_docker_files(tmp_path, files))
        assert set(first.values()) == {"written"}

        second = dict(write_docker_files(tmp_path, files))
        assert set(second.values()) == {"skipped"}

        third = dict(write_docker_files(tmp_path, files, force=True))
        assert set(third.values()) == {"overwritten"}

    def test_creates_the_deploy_directory(self, tmp_path):
        write_docker_files(tmp_path, docker_files("demo"))
        assert (tmp_path / "deploy").is_dir()


# =============================================================================
# .feather-templates
# =============================================================================


class TestTemplatesLink:
    def test_creates_the_link(self, tmp_path):
        status, detail = ensure_templates_link(tmp_path)
        assert status == "created"
        link = tmp_path / LINK_NAME
        assert link.is_symlink()
        assert link.resolve() == feather_templates_dir()

    def test_is_idempotent(self, tmp_path):
        ensure_templates_link(tmp_path)
        status, _ = ensure_templates_link(tmp_path)
        assert status == "current"

    def test_replaces_a_stale_link(self, tmp_path):
        (tmp_path / LINK_NAME).symlink_to(tmp_path, target_is_directory=True)
        status, _ = ensure_templates_link(tmp_path)
        assert status == "updated"
        assert (tmp_path / LINK_NAME).resolve() == feather_templates_dir()

    def test_replaces_a_dangling_link(self, tmp_path):
        (tmp_path / LINK_NAME).symlink_to(tmp_path / "gone", target_is_directory=True)
        status, _ = ensure_templates_link(tmp_path)
        assert status == "updated"

    def test_leaves_a_real_directory_alone(self, tmp_path):
        # This is what the Docker image has: a COPY of the templates.
        real = tmp_path / LINK_NAME
        real.mkdir()
        (real / "marker.html").write_text("x")

        status, _ = ensure_templates_link(tmp_path)
        assert status == "directory"
        assert (real / "marker.html").exists()
        assert not real.is_symlink()

    def test_refuses_a_regular_file(self, tmp_path):
        (tmp_path / LINK_NAME).write_text("not a directory")
        status, detail = ensure_templates_link(tmp_path)
        assert status == "error"
        assert LINK_NAME in detail


# =============================================================================
# feather env check
# =============================================================================


class TestCollectEnvRefs:
    def test_get_with_default_is_optional(self):
        refs = collect_env_refs('import os\nX = os.environ.get("FOO", "bar")\n')
        assert refs["FOO"].required is False
        assert refs["FOO"].default == "bar"

    def test_get_without_default_is_required(self):
        refs = collect_env_refs('import os\nX = os.environ.get("FOO")\n')
        assert refs["FOO"].required is True

    def test_subscript_is_required(self):
        refs = collect_env_refs('import os\nX = os.environ["FOO"]\n')
        assert refs["FOO"].required is True

    def test_getenv(self):
        refs = collect_env_refs('import os\nX = os.getenv("FOO", "bar")\n')
        assert refs["FOO"].default == "bar"

    def test_any_read_without_a_fallback_wins(self):
        refs = collect_env_refs(
            'import os\nA = os.environ.get("FOO", "d")\nB = os.environ.get("FOO")\n'
        )
        assert refs["FOO"].required is True

    def test_non_literal_keys_are_ignored(self):
        refs = collect_env_refs("import os\nk = 'FOO'\nX = os.environ.get(k)\n")
        assert refs == {}

    def test_bad_syntax_raises_a_clean_error(self):
        import click

        with pytest.raises(click.ClickException):
            collect_env_refs("def (:\n")


@pytest.fixture
def env_project(tmp_path, monkeypatch):
    """A project whose config.py reads a couple of uniquely named keys."""
    (tmp_path / "config.py").write_text(
        "import os\n"
        "\n"
        "class Config:\n"
        '    NEEDED = os.environ.get("FEATHERTEST_NEEDED")\n'
        '    OPTIONAL = os.environ.get("FEATHERTEST_OPTIONAL", "fallback")\n'
    )
    for key in ("FEATHERTEST_NEEDED", "FEATHERTEST_OPTIONAL", "FEATHERTEST_EXTRA"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


class TestEnvCheckCommand:
    def test_requires_a_config_py(self, tmp_path):
        result = CliRunner().invoke(env_group, ["check", "--path", str(tmp_path)])
        assert result.exit_code != 0
        assert "config.py" in result.output

    def test_reports_a_missing_required_key(self, env_project):
        result = CliRunner().invoke(env_group, ["check", "--path", str(env_project)])
        assert result.exit_code == 1
        assert "FEATHERTEST_NEEDED" in result.output
        assert "MISSING" in result.output

    def test_passes_when_the_key_is_set(self, env_project, monkeypatch):
        monkeypatch.setenv("FEATHERTEST_NEEDED", "value")
        result = CliRunner().invoke(env_group, ["check", "--path", str(env_project)])
        assert result.exit_code == 0, result.output
        assert "All required keys are set." in result.output

    def test_reads_the_projects_env_file(self, env_project):
        (env_project / ".env").write_text("FEATHERTEST_NEEDED=from-file\n")
        result = CliRunner().invoke(env_group, ["check", "--path", str(env_project)])
        assert result.exit_code == 0, result.output

    def test_explicit_env_file(self, env_project):
        (env_project / "prod.env").write_text("FEATHERTEST_NEEDED=x\n")
        result = CliRunner().invoke(
            env_group, ["check", "--path", str(env_project), "--env-file", "prod.env"]
        )
        assert result.exit_code == 0, result.output

    def test_missing_env_file_is_an_error(self, env_project):
        result = CliRunner().invoke(
            env_group, ["check", "--path", str(env_project), "--env-file", "nope.env"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_optional_key_reports_its_default(self, env_project, monkeypatch):
        monkeypatch.setenv("FEATHERTEST_NEEDED", "value")
        result = CliRunner().invoke(env_group, ["check", "--path", str(env_project)])
        assert "fallback" in result.output

    def test_json_output(self, env_project):
        import json

        result = CliRunner().invoke(env_group, ["check", "--path", str(env_project), "--json"])
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "FEATHERTEST_NEEDED" in payload["missing"]
        assert any(row["key"] == "FEATHERTEST_OPTIONAL" for row in payload["keys"])

    def test_reports_keys_the_config_never_reads(self, env_project, monkeypatch):
        monkeypatch.setenv("FEATHERTEST_NEEDED", "value")
        (env_project / ".env").write_text("FEATHERTEST_EXTRA=1\n")
        result = CliRunner().invoke(env_group, ["check", "--path", str(env_project)])
        assert "FEATHERTEST_EXTRA" in result.output
        assert "not read by config.py" in result.output

    def test_compose_supplied_keys_do_not_fail(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        (tmp_path / "config.py").write_text(
            'import os\nD = os.environ.get("DATABASE_URL")\n'
        )
        result = CliRunner().invoke(env_group, ["check", "--path", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "compose supplies" in result.output

    def test_flask_env_is_not_required(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FLASK_ENV", raising=False)
        (tmp_path / "config.py").write_text(
            'import os\nE = os.environ.get("FLASK_ENV")\n'
        )
        result = CliRunner().invoke(env_group, ["check", "--path", str(tmp_path)])
        assert result.exit_code == 0, result.output


# =============================================================================
# The old Render command is gone
# =============================================================================


class TestRenderRemoved:
    def test_no_deploy_module(self):
        with pytest.raises(ImportError):
            import feather.cli.deploy  # noqa: F401

    def test_cli_has_docker_and_env_but_no_deploy(self):
        from feather.cli import cli

        assert "docker" in cli.commands
        assert "env" in cli.commands
        assert "deploy" not in cli.commands

    def test_help_does_not_mention_render(self):
        from feather.cli import cli

        result = CliRunner().invoke(cli, ["--help"])
        assert "render" not in result.output.lower()
        assert "docker init" in result.output


def test_environ_is_not_mutated_by_the_helpers(tmp_path):
    """Nothing here should leak into the process environment."""
    before = dict(os.environ)
    write_docker_files(tmp_path, docker_files("demo"))
    ensure_templates_link(tmp_path)
    assert dict(os.environ) == before


class TestJobEnvOnBothServices:
    """web enqueues and worker consumes; both must name the same backend.

    Setting JOB_BACKEND only on the worker is the easy misconfiguration: web
    falls back to config.py's default (the in-process thread backend) and the
    jobs it "queues" never reach the worker at all.
    """

    def test_web_and_worker_agree(self):
        compose = next(
            f for f in docker_files("demo", worker=True) if f.path == "docker-compose.yml"
        ).content
        assert compose.count("JOB_BACKEND: rq") == 2
        assert compose.count("JOB_SERIALIZER: json") == 2

    def test_no_job_env_without_a_worker(self):
        compose = next(
            f for f in docker_files("demo", worker=False) if f.path == "docker-compose.yml"
        ).content
        assert "JOB_BACKEND" not in compose
        assert "JOB_SERIALIZER" not in compose


class TestProxyKeysInEnvExample:
    """A reverse proxy makes the Host header attacker-controllable."""

    def test_trusted_hosts_and_oauth_callback_are_listed(self):
        body = render_env_example("demo", domain="app.example.com")
        assert "TRUSTED_HOSTS=app.example.com" in body
        assert "OAUTH_CALLBACK_URL=https://app.example.com/auth/google/callback" in body

    def test_they_are_not_marked_compose_supplied(self):
        # compose does not set them, so `feather env check` must be able to
        # report them as missing.
        from feather.cli._docker_templates import COMPOSE_PROVIDED_KEYS

        assert "TRUSTED_HOSTS" not in COMPOSE_PROVIDED_KEYS
        assert "OAUTH_CALLBACK_URL" not in COMPOSE_PROVIDED_KEYS
