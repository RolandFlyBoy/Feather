"""Optional dependency extras (0.9.8).

weasyprint, google-cloud-storage, psycopg2, redis, rq, resend, gunicorn and
pytest are no longer hard dependencies. Every module that imports one must
fail with an actionable message naming the exact install command instead of
a bare ImportError traceback.
"""

import sys
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def hide_module(name: str):
    """Make feather._optional.require(name) behave as if it were missing."""
    import feather._optional as optional

    real = optional.import_module

    def fake(module, *args, **kwargs):
        if module == name or module.startswith(name + "."):
            raise ImportError(f"No module named {module!r}")
        return real(module, *args, **kwargs)

    return patch.object(optional, "import_module", fake)


class TestExtrasMetadata:
    """feather._optional knows which extra ships which package."""

    def test_every_documented_extra_is_declared(self):
        from feather._optional import EXTRAS

        assert set(EXTRAS) == {"pdf", "gcs", "postgres", "redis", "email", "ratelimit", "prod", "test"}

    def test_extras_map_to_distributions(self):
        from feather._optional import EXTRAS

        assert EXTRAS["pdf"] == ("weasyprint",)
        assert EXTRAS["gcs"] == ("google-cloud-storage",)
        assert EXTRAS["postgres"] == ("psycopg2-binary",)
        assert EXTRAS["redis"] == ("redis", "rq")
        assert EXTRAS["email"] == ("resend",)
        assert EXTRAS["ratelimit"] == ("flask-limiter",)
        assert EXTRAS["prod"] == ("gunicorn",)
        assert EXTRAS["test"] == ("pytest", "pytest-cov")

    def test_pyproject_declares_the_same_extras(self):
        import tomllib
        from pathlib import Path

        from feather._optional import EXTRAS

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        optional = data["project"]["optional-dependencies"]

        for extra in EXTRAS:
            assert extra in optional, f"pyproject.toml is missing the '{extra}' extra"
        assert "all" in optional
        assert "dev" in optional

    def test_heavy_packages_are_not_core_dependencies(self):
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        core = " ".join(data["project"]["dependencies"]).lower()

        for package in (
            "weasyprint",
            "google-cloud-storage",
            "psycopg2-binary",
            "redis",
            "rq",
            "resend",
            "gunicorn",
            "pytest",
        ):
            assert package not in core, f"{package} must be an extra, not a core dependency"

    def test_dev_extra_pulls_in_everything_the_tests_need(self):
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        optional = data["project"]["optional-dependencies"]

        # Resolve the self-referential extras (dev -> all -> test -> pytest).
        def resolve(name, seen=frozenset()):
            requirements = set()
            for item in optional[name]:
                item = item.strip().lower()
                if item.startswith("feather-framework["):
                    for nested in item[len("feather-framework["):].rstrip("]").split(","):
                        nested = nested.strip()
                        if nested not in seen:
                            requirements |= resolve(nested, seen | {nested})
                else:
                    requirements.add(item)
            return requirements

        dev = " ".join(sorted(resolve("dev")))
        # The framework's own suite imports rq, redis, google.cloud and pytest.
        for package in ("pytest", "rq", "redis", "google-cloud-storage", "weasyprint"):
            assert package in dev, f"the dev extra must install {package}"


class TestRequire:
    """feather._optional.require() gives an actionable error."""

    def test_require_returns_the_module_when_installed(self):
        from feather._optional import require

        assert require("json") is sys.modules["json"]

    def test_require_names_the_install_command(self):
        from feather._optional import MissingDependencyError, require

        with hide_module("weasyprint"), pytest.raises(MissingDependencyError) as exc:
            require("weasyprint", feature="PDF rendering")

        message = str(exc.value)
        assert "pip install 'feather-framework[pdf]'" in message
        assert "PDF rendering" in message
        assert "weasyprint" in message

    def test_missing_dependency_error_is_an_import_error(self):
        """Existing `except ImportError` handlers keep working."""
        from feather._optional import MissingDependencyError

        assert issubclass(MissingDependencyError, ImportError)

    def test_unknown_module_still_gets_a_usable_message(self):
        from feather._optional import MissingDependencyError, require

        with pytest.raises(MissingDependencyError) as exc:
            require("definitely_not_a_real_module_xyz")
        assert "definitely_not_a_real_module_xyz" in str(exc.value)


class TestInstalledExtras:
    """Report which extras are present, for security-check/doctor output."""

    def test_installed_extras_covers_every_extra(self):
        from feather._optional import EXTRAS, installed_extras

        report = installed_extras()
        assert set(report) == set(EXTRAS)
        for entry in report.values():
            assert "installed" in entry
            assert "packages" in entry

    def test_redis_extra_detected_in_the_dev_environment(self):
        """The dev extra installs rq and redis, so this must report installed."""
        pytest.importorskip("rq")
        from feather._optional import installed_extras

        assert installed_extras()["redis"]["installed"] is True

    def test_summary_lines_are_human_readable(self):
        from feather._optional import extras_summary

        text = extras_summary()
        assert "pdf" in text and "gcs" in text


class TestBackendsFailActionably:
    """Each backend that needs an extra says how to install it."""

    def test_redis_cache_without_redis(self):
        from feather._optional import MissingDependencyError
        from feather.cache.redis import RedisCache

        with hide_module("redis"), pytest.raises(MissingDependencyError) as exc:
            RedisCache(url="redis://localhost:6379/0")
        assert "feather-framework[redis]" in str(exc.value)

    def test_rq_queue_without_rq(self):
        from feather._optional import MissingDependencyError
        from feather.jobs.rq import RQQueue

        with hide_module("rq"), pytest.raises(MissingDependencyError) as exc:
            RQQueue(redis_url="redis://localhost:6379/0")
        assert "feather-framework[redis]" in str(exc.value)

    def test_rq_queue_without_redis(self):
        from feather._optional import MissingDependencyError
        from feather.jobs.rq import RQQueue

        with hide_module("redis"), pytest.raises(MissingDependencyError) as exc:
            RQQueue(redis_url="redis://localhost:6379/0")
        assert "feather-framework[redis]" in str(exc.value)

    def test_gcs_storage_without_google_cloud_storage(self):
        from feather._optional import MissingDependencyError
        from feather.storage.gcs import GCSStorage

        with hide_module("google.cloud"), pytest.raises(MissingDependencyError) as exc:
            GCSStorage("some-bucket")
        assert "feather-framework[gcs]" in str(exc.value)

    def test_scheduler_without_rq_scheduler(self):
        from feather._optional import MissingDependencyError, require

        with hide_module("rq_scheduler"), pytest.raises(MissingDependencyError) as exc:
            require("rq_scheduler", feature="Scheduled jobs")
        message = str(exc.value)
        assert "pip install rq-scheduler" in message
        assert "Scheduled jobs" in message


class TestSecurityCheckReportsExtras:
    def test_run_checks_includes_extras(self, tmp_path):
        from feather.cli.security_check import run_checks

        result = run_checks(tmp_path, None)
        assert "extras" in result
        assert set(result["extras"]) == {"pdf", "gcs", "postgres", "redis", "email", "ratelimit", "prod", "test"}

    def test_extras_check_line_present(self, tmp_path):
        from feather.cli.security_check import run_checks

        result = run_checks(tmp_path, None)
        names = [c["name"] for c in result["checks"]]
        assert "extras" in names


class TestVersionCommandReportsExtras:
    def test_version_output_lists_extras(self):
        from click.testing import CliRunner

        from feather.cli import cli

        result = CliRunner().invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "extras installed:" in result.output


class TestRequirementSpec:
    """What a generated requirements.txt must say from 0.9.8 on."""

    def test_bare_spec(self):
        from feather._optional import requirement_spec

        assert requirement_spec("0.9.8") == "feather-framework==0.9.8"

    def test_extras_are_sorted_and_deduplicated(self):
        from feather._optional import requirement_spec

        assert (
            requirement_spec("0.9.8", ["redis", "email", "redis"])
            == "feather-framework[email,redis]==0.9.8"
        )

    def test_unpinned(self):
        from feather._optional import requirement_spec

        assert requirement_spec(extras=["pdf"]) == "feather-framework[pdf]"

    def test_unknown_extra_fails_loudly(self):
        from feather._optional import requirement_spec

        with pytest.raises(ValueError) as exc:
            requirement_spec("0.9.8", ["redis", "nope"])
        assert "nope" in str(exc.value)

    def test_all_is_accepted(self):
        from feather._optional import requirement_spec

        assert requirement_spec("0.9.8", ["all"]) == "feather-framework[all]==0.9.8"
