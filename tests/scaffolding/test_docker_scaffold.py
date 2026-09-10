"""Scaffolding tests for the 0.9.7 Docker deployment layout.

``feather new`` writes the whole deployment layout (Dockerfile, both compose
files, the Caddyfile, the deploy scripts and .env.example). These tests check
the parts that only fail in production if they are wrong:

* every file is generated, and the shell scripts are executable and parse
* ``docker compose config`` accepts both compose files (skipped without Docker)
* every generated healthcheck points at ``/health``, which checks the database
* ``static/css/app.css`` contains no absolute filesystem path, and a real
  Tailwind build with ``.feather-templates`` in place emits a class that only
  exists in a framework component template
"""

import os
import shutil
import stat
import subprocess

import pytest

pytestmark = pytest.mark.scaffolding


FULL = {
    "database": "postgresql",
    "db_url": "postgresql://localhost/testapp",
    "include_auth": True,
    "tenant_mode": "single",
    "admin_email": "admin@test.com",
    "include_cache": True,
    "include_jobs": True,
}

SIMPLE = {"database": "none"}

DOCKER_FILES = (
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    "docker-compose.dev.yml",
    "deploy/Caddyfile",
    "deploy/deploy.sh",
    "deploy/backup.sh",
    ".env.example",
)

#: A Tailwind class used by feather/templates/components/confirm_modal.html
#: and by nothing the scaffold writes. If it survives into the built CSS,
#: Tailwind really did scan the framework's own templates.
FRAMEWORK_ONLY_CLASS = "bg-gray-500"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


class TestDockerFilesGenerated:
    """The deployment layout ships with every new project."""

    @pytest.mark.parametrize("name", DOCKER_FILES)
    def test_file_exists(self, scaffold_project, name):
        project = scaffold_project(FULL)
        assert (project / name).exists(), f"{name} was not generated"

    @pytest.mark.parametrize("name", DOCKER_FILES)
    def test_file_exists_for_minimal_app(self, scaffold_project, name):
        # A no-database app still gets a deployable layout.
        project = scaffold_project(SIMPLE)
        assert (project / name).exists(), f"{name} was not generated"

    def test_scripts_are_executable(self, scaffold_project):
        project = scaffold_project(FULL)
        for script in ("deploy/deploy.sh", "deploy/backup.sh"):
            mode = (project / script).stat().st_mode
            assert mode & stat.S_IXUSR, f"{script} is not executable"

    @pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not on PATH")
    @pytest.mark.parametrize("script", ["deploy/deploy.sh", "deploy/backup.sh"])
    def test_scripts_parse(self, scaffold_project, script):
        project = scaffold_project(FULL)
        result = subprocess.run(
            ["bash", "-n", str(project / script)],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"{script}:\n{result.stderr}"

    def test_dockerignore_excludes_secrets_and_the_templates_link(self, scaffold_project):
        project = scaffold_project(FULL)
        body = (project / ".dockerignore").read_text()
        for entry in (".env", "venv/", "node_modules/", ".feather-templates"):
            assert entry in body, f"{entry} missing from .dockerignore"

    def test_gitignore_lists_the_templates_link(self, scaffold_project):
        project = scaffold_project(FULL)
        assert ".feather-templates" in (project / ".gitignore").read_text()

    def test_worker_target_only_when_jobs_are_enabled(self, scaffold_project):
        with_jobs = scaffold_project(FULL)
        assert "AS worker" in (with_jobs / "Dockerfile").read_text()
        assert "worker:" in (with_jobs / "docker-compose.yml").read_text()

        without = scaffold_project(SIMPLE)
        assert "AS worker" not in (without / "Dockerfile").read_text()
        assert "target: worker" not in (without / "docker-compose.yml").read_text()

    def test_no_render_yaml(self, scaffold_project):
        project = scaffold_project(FULL)
        assert not (project / "render.yaml").exists()


class TestHealthPath:
    """Every generated healthcheck points at the endpoint that checks the DB."""

    def test_dockerfile_healthcheck(self, scaffold_project):
        project = scaffold_project(FULL)
        dockerfile = (project / "Dockerfile").read_text()
        assert "HEALTHCHECK" in dockerfile
        assert "/health" in dockerfile
        # The scaffolded alias must not be what the container polls: it used
        # to answer {"status": "ok"} without touching the database.
        assert "/api/health" not in dockerfile

    def test_deploy_script_and_caddyfile_reference_health(self, scaffold_project):
        project = scaffold_project(FULL)
        assert "/health" in (project / "deploy/deploy.sh").read_text()
        assert "/health" in (project / "deploy/Caddyfile").read_text()
        assert "/api/health" not in (project / "deploy/Caddyfile").read_text()

    def test_api_health_route_delegates_to_the_framework(self, scaffold_project):
        project = scaffold_project(FULL)
        route = (project / "routes/api/health.py").read_text()
        assert "from feather.core.health import health_check" in route
        assert "return health_check()" in route
        assert '{"status": "ok"}' not in route


class TestEnvExample:
    """.env.example is the source of truth both production apps lacked."""

    def test_documents_compose_supplied_keys(self, scaffold_project):
        project = scaffold_project(FULL)
        body = (project / ".env.example").read_text()
        assert "DOMAIN=" in body
        assert "POSTGRES_PASSWORD=" in body
        for key in ("DATABASE_URL", "REDIS_URL", "WEB_CONCURRENCY"):
            assert key in body, f"{key} not mentioned in .env.example"

    def test_secrets_are_blank(self, scaffold_project):
        project = scaffold_project(FULL)
        body = (project / ".env.example").read_text()
        assert "SECRET_KEY=\n" in body
        assert "dev-secret-key-change-in-production" not in body


class TestRequirementsPin:
    """Images must build the framework version the project was written for."""

    def test_pins_the_installed_version(self, scaffold_project):
        from feather.cli.new import _get_feather_version

        project = scaffold_project(FULL)
        reqs = (project / "requirements.txt").read_text()
        # Since 0.9.8 the line carries the extras this app needs, so it reads
        # feather-framework[email,postgres,...]==X.Y.Z rather than a bare pin.
        line = next(l for l in reqs.splitlines() if l.startswith("feather-framework"))
        assert line.endswith(f"=={_get_feather_version()}")
        assert line.startswith("feather-framework[")

    def test_names_the_extras_the_app_enabled(self, scaffold_project):
        """A feature whose extra is missing fails at startup, not at install.

        FULL turns on Postgres plus jobs and cache, so psycopg2 and redis
        have to be named or the built image cannot connect or enqueue.
        """
        project = scaffold_project(FULL)
        extras = self._extras(project)
        assert {"postgres", "redis", "prod", "test"} <= extras

    def test_email_and_storage_extras_follow_their_features(self, scaffold_project):
        project = scaffold_project(
            {**FULL, "include_email": True, "include_storage": True, "storage_backend": "gcs"}
        )
        extras = self._extras(project)
        assert "email" in extras, "resend is not installed without the email extra"
        assert "gcs" in extras, "google-cloud-storage is not installed without the gcs extra"

    @staticmethod
    def _extras(project) -> set:
        line = next(
            l for l in (project / "requirements.txt").read_text().splitlines()
            if l.startswith("feather-framework")
        )
        return set(line.split("[", 1)[1].split("]", 1)[0].split(","))

    def test_minimal_app_does_not_ask_for_what_it_lacks(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        extras = self._extras(project)
        # No database, no cache, no jobs, no email, no GCS.
        assert extras.isdisjoint({"postgres", "redis", "email", "gcs", "pdf"})
        # Every app is still meant to be deployable and testable.
        assert {"prod", "test"} <= extras

    def test_dockerfile_installs_the_pinned_framework_first(self, scaffold_project):
        project = scaffold_project(FULL)
        dockerfile = (project / "Dockerfile").read_text()
        # Feather goes on its own layer so the frontend stage can copy its
        # templates out of the base image.
        assert "grep '^feather-framework' requirements.txt" in dockerfile
        assert "COPY --from=base" in dockerfile
        assert ".feather-templates" in dockerfile


@pytest.mark.skipif(not _docker_available(), reason="docker is not on PATH")
class TestComposeParses:
    """`docker compose config` accepts what we generate."""

    @pytest.mark.parametrize("compose_file", ["docker-compose.yml", "docker-compose.dev.yml"])
    def test_compose_config(self, scaffold_project, compose_file):
        project = scaffold_project(FULL)
        # Compose reads ./.env for ${...} interpolation and the web service
        # declares `env_file: .env`, so the file has to exist. The scaffold
        # writes one; top up the two host-side keys compose requires.
        env_path = project / ".env"
        env_path.write_text(
            env_path.read_text() + "\nDOMAIN=example.com\nPOSTGRES_PASSWORD=testpassword\n"
        )

        result = subprocess.run(
            ["docker", "compose", "-f", compose_file, "config"],
            cwd=str(project), capture_output=True, text=True, timeout=180,
        )
        assert result.returncode == 0, (
            f"docker compose config rejected {compose_file}:\n{result.stderr}"
        )


class TestTailwindSourcePath:
    """The bug that silently stripped every framework component style."""

    def test_app_css_has_no_absolute_path(self, scaffold_project):
        project = scaffold_project(FULL)
        css = (project / "static/css/app.css").read_text()
        for line in css.splitlines():
            if line.startswith("@source"):
                assert '"/' not in line, (
                    f"absolute path baked into app.css: {line!r}. "
                    "It does not exist in the Docker image, so Tailwind emits "
                    "none of the framework component classes."
                )
        assert '@source "../../.feather-templates/**/*.html";' in css

    def test_app_css_does_not_mention_site_packages(self, scaffold_project):
        project = scaffold_project(FULL)
        css = (project / "static/css/app.css").read_text()
        assert "site-packages" not in css
        assert os.path.dirname(os.path.abspath(__file__)) not in css


@pytest.mark.skipif(shutil.which("npm") is None, reason="npm is not on PATH")
class TestFrameworkClassesSurviveTheBuild:
    """A real Tailwind build emits the framework components' classes.

    The install plus build takes on the order of a minute, so only one app
    type is built. This is the end-to-end proof that the `.feather-templates`
    indirection works: without it the built CSS silently lacks every class
    that only Feather's own component templates use.
    """

    def test_built_css_contains_a_framework_only_class(self, scaffold_project):
        from feather.cli._templates_link import ensure_templates_link

        project = scaffold_project(SIMPLE)

        status, detail = ensure_templates_link(project)
        assert status in ("created", "updated", "current", "directory"), detail

        install = subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", "--prefer-offline"],
            cwd=str(project), capture_output=True, text=True, timeout=900,
        )
        assert install.returncode == 0, f"npm install failed:\n{install.stderr}"

        build = subprocess.run(
            ["npx", "vite", "build"],
            cwd=str(project), capture_output=True, text=True, timeout=900,
        )
        assert build.returncode == 0, f"vite build failed:\n{build.stdout}\n{build.stderr}"

        css_files = list((project / "static/dist").glob("styles-*.css"))
        assert css_files, "vite build produced no stylesheet"
        css = css_files[0].read_text()

        assert FRAMEWORK_ONLY_CLASS in css, (
            f"{FRAMEWORK_ONLY_CLASS!r} is missing from the built CSS. It is used "
            "only by feather/templates/components/, so Tailwind did not scan the "
            "framework templates through .feather-templates."
        )


class TestProxyHardeningKeys:
    """The generated ProductionConfig reads the keys a proxy makes necessary.

    `feather env check` only knows about keys config.py reads, so if these are
    not in the config they can never be reported missing.
    """

    def test_production_config_reads_trusted_hosts(self, scaffold_project):
        project = scaffold_project(FULL)
        config = (project / "config.py").read_text()
        assert 'TRUSTED_HOSTS = os.environ.get("TRUSTED_HOSTS")' in config

    def test_production_config_reads_oauth_callback_url(self, scaffold_project):
        project = scaffold_project(FULL)
        config = (project / "config.py").read_text()
        assert 'OAUTH_CALLBACK_URL = os.environ.get("OAUTH_CALLBACK_URL")' in config

    def test_env_example_lists_them(self, scaffold_project):
        project = scaffold_project(FULL)
        body = (project / ".env.example").read_text()
        assert "TRUSTED_HOSTS=" in body
        assert "OAUTH_CALLBACK_URL=" in body

    def test_env_check_flags_them_when_unset(self, scaffold_project, monkeypatch):
        from click.testing import CliRunner

        from feather.cli.env import env_group

        project = scaffold_project(FULL)
        for key in ("TRUSTED_HOSTS", "OAUTH_CALLBACK_URL"):
            monkeypatch.delenv(key, raising=False)

        result = CliRunner().invoke(env_group, ["check", "--path", str(project), "--json"])
        import json

        payload = json.loads(result.output)
        assert "TRUSTED_HOSTS" in payload["missing"]
        assert "OAUTH_CALLBACK_URL" in payload["missing"]
