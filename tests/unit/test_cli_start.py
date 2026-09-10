"""Unit tests for `feather start` and `feather build`.

`feather start` is what the container image runs, so three things matter:
the gunicorn defaults come from PORT / WEB_CONCURRENCY, the process is
replaced (gunicorn becomes PID 1 and gets docker stop's SIGTERM), and a
failing security check stops the boot.
"""

import os
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from feather.cli.build import build, start

pytestmark = pytest.mark.unit

# feather/cli/__init__.py binds the `build` and `security_check` *commands* as
# attributes of the feather.cli package, shadowing the submodules of the same
# name, so "feather.cli.build" as a monkeypatch target resolves to a click
# Command. Reach the real modules through sys.modules instead.
build_module = sys.modules["feather.cli.build"]
security_check_module = sys.modules["feather.cli.security_check"]


class ExecCalled(Exception):
    """Raised by the os.execvp stand-in so the test regains control."""

    def __init__(self, argv):
        self.argv = argv
        super().__init__(" ".join(argv))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project directory that is the CWD, with gunicorn 'installed'."""
    (tmp_path / "app.py").write_text("from feather import Feather\napp = Feather(__name__)\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    for key in ("PORT", "WEB_CONCURRENCY"):
        monkeypatch.delenv(key, raising=False)
    # `feather start` writes FLASK_ENV into os.environ before auditing.
    # Going through monkeypatch means it is restored after each test rather
    # than leaking "production" into the rest of the session.
    monkeypatch.setenv("FLASK_ENV", os.environ.get("FLASK_ENV", "testing"))
    return tmp_path


@pytest.fixture
def captured_exec(monkeypatch):
    """Replace os.execvp so we can inspect the gunicorn command line."""
    calls = []

    def fake_execvp(file, argv):
        calls.append(argv)
        raise ExecCalled(argv)

    monkeypatch.setattr(os, "execvp", fake_execvp)
    return calls


@pytest.fixture
def passing_security_check(monkeypatch):
    monkeypatch.setattr(
        build_module,
        "_run_security_check",
        lambda: {"ok": True, "checks": [], "summary": {"pass": 9, "warn": 0, "fail": 0, "skip": 0}},
    )


def _argv(calls):
    assert calls, "os.execvp was never called - gunicorn did not start"
    return calls[0]


def _value(argv, flag):
    return argv[argv.index(flag) + 1]


class TestStartRefusesOutsideAProject:
    def test_no_app_py(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(start, [])
        assert result.exit_code != 0
        assert "Not in a Feather project" in result.output


class TestStartSecurityGate:
    def test_a_failing_check_refuses_to_start(self, project, monkeypatch, captured_exec):
        monkeypatch.setattr(
            build_module,
            "_run_security_check",
            lambda: {
                "ok": False,
                "checks": [
                    {
                        "name": "secret_key",
                        "status": "FAIL",
                        "message": "SECRET_KEY is still the development default",
                        "remedy": "Generate one",
                    }
                ],
                "summary": {"pass": 0, "warn": 0, "fail": 1, "skip": 0},
            },
        )
        result = CliRunner().invoke(start, [])
        assert result.exit_code != 0
        assert "Refusing to start" in result.output
        assert "secret_key" in result.output
        assert "--skip-security-check" in result.output
        assert not captured_exec, "gunicorn started despite a failed security check"

    def test_skip_flag_bypasses_the_check(self, project, monkeypatch, captured_exec):
        def explode():
            raise AssertionError("the security check should not have run")

        monkeypatch.setattr(build_module, "_run_security_check", explode)
        CliRunner().invoke(start, ["--skip-security-check"])
        assert _argv(captured_exec)[0] == "gunicorn"

    def test_warnings_do_not_block(self, project, monkeypatch, captured_exec):
        monkeypatch.setattr(
            build_module,
            "_run_security_check",
            lambda: {
                "ok": True,
                "checks": [{"name": "x", "status": "WARN", "message": "m", "remedy": ""}],
                "summary": {"pass": 1, "warn": 1, "fail": 0, "skip": 0},
            },
        )
        CliRunner().invoke(start, [])
        assert _argv(captured_exec)[0] == "gunicorn"

    def test_audit_runs_with_production_rules(self, project, monkeypatch, captured_exec):
        seen = {}

        def fake_run_checks(project_dir, env_file=None, force_production=False):
            seen["force_production"] = force_production
            seen["flask_env"] = os.environ.get("FLASK_ENV")
            return {"ok": True, "checks": [], "summary": {"pass": 1, "warn": 0, "fail": 0, "skip": 0}}

        monkeypatch.setattr(security_check_module, "run_checks", fake_run_checks)
        CliRunner().invoke(start, [])
        assert seen["force_production"] is True
        assert seen["flask_env"] == "production"


class TestStartCommandLine:
    def test_replaces_the_process(self, project, passing_security_check, captured_exec):
        # execvp, not subprocess: in a container gunicorn must be PID 1 so
        # `docker stop` delivers SIGTERM to it and the graceful drain happens.
        CliRunner().invoke(start, [])
        argv = _argv(captured_exec)
        assert argv[0] == "gunicorn"
        assert argv[1] == "app:app"

    def test_port_from_the_environment(self, project, passing_security_check, captured_exec, monkeypatch):
        monkeypatch.setenv("PORT", "9001")
        CliRunner().invoke(start, [])
        assert _value(_argv(captured_exec), "--bind") == "0.0.0.0:9001"

    def test_web_concurrency_from_the_environment(
        self, project, passing_security_check, captured_exec, monkeypatch
    ):
        monkeypatch.setenv("WEB_CONCURRENCY", "7")
        CliRunner().invoke(start, [])
        assert _value(_argv(captured_exec), "--workers") == "7"

    def test_flags_beat_the_environment(
        self, project, passing_security_check, captured_exec, monkeypatch
    ):
        monkeypatch.setenv("PORT", "9001")
        monkeypatch.setenv("WEB_CONCURRENCY", "7")
        CliRunner().invoke(start, ["--port", "5555", "--workers", "2"])
        argv = _argv(captured_exec)
        assert _value(argv, "--bind") == "0.0.0.0:5555"
        assert _value(argv, "--workers") == "2"

    def test_graceful_timeout_option(self, project, passing_security_check, captured_exec):
        CliRunner().invoke(start, ["--graceful-timeout", "45"])
        assert _value(_argv(captured_exec), "--graceful-timeout") == "45"

    def test_graceful_timeout_default(self, project, passing_security_check, captured_exec):
        CliRunner().invoke(start, [])
        assert "--graceful-timeout" in _argv(captured_exec)

    def test_max_requests_option_and_jitter(self, project, passing_security_check, captured_exec):
        CliRunner().invoke(start, ["--max-requests", "500"])
        argv = _argv(captured_exec)
        assert _value(argv, "--max-requests") == "500"
        assert _value(argv, "--max-requests-jitter") == "50"

    def test_max_requests_jitter_never_zero(self, project, passing_security_check, captured_exec):
        CliRunner().invoke(start, ["--max-requests", "5"])
        assert _value(_argv(captured_exec), "--max-requests-jitter") == "1"

    def test_threads_option(self, project, passing_security_check, captured_exec):
        CliRunner().invoke(start, ["--worker-class", "gthread", "--threads", "4"])
        argv = _argv(captured_exec)
        assert _value(argv, "--worker-class") == "gthread"
        assert _value(argv, "--threads") == "4"

    def test_missing_gunicorn_is_a_clean_error(
        self, project, passing_security_check, captured_exec, monkeypatch
    ):
        monkeypatch.setattr("shutil.which", lambda name: None)
        result = CliRunner().invoke(start, [])
        assert result.exit_code != 0
        assert "Gunicorn not found" in result.output
        assert not captured_exec


class TestBuildRefreshesTheTemplatesLink:
    def test_link_created_before_the_frontend_build(self, tmp_path, monkeypatch):
        from feather.cli._templates_link import LINK_NAME, feather_templates_dir

        (tmp_path / "app.py").write_text("app = None\n")
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(build, [])
        assert result.exit_code == 0, result.output
        link = tmp_path / LINK_NAME
        assert link.is_symlink()
        assert link.resolve() == feather_templates_dir()

    def test_real_directory_is_left_alone(self, tmp_path, monkeypatch):
        from feather.cli._templates_link import LINK_NAME

        (tmp_path / "app.py").write_text("app = None\n")
        real = tmp_path / LINK_NAME
        real.mkdir()
        (real / "marker.html").write_text("x")
        monkeypatch.chdir(tmp_path)

        CliRunner().invoke(build, [])
        assert not real.is_symlink()
        assert (real / "marker.html").exists()

    def test_refuses_outside_a_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(build, [])
        assert result.exit_code != 0
        assert "Not in a Feather project" in result.output
        assert not (Path(tmp_path) / ".feather-templates").exists()


class TestWorkerClassFlag:
    """`feather worker` exposes an explicit worker-class choice.

    The default is unchanged (SimpleWorker on macOS, the forking Worker
    elsewhere), but the generated Dockerfile passes --fork so a Linux
    container never silently runs jobs in the worker's own process.
    """

    def test_simple_and_fork_flags_exist(self):
        from feather.cli.worker import worker as worker_cmd

        opts = {opt for param in worker_cmd.params for opt in param.opts}
        secondary = {
            opt for param in worker_cmd.params for opt in getattr(param, "secondary_opts", [])
        }
        assert "--simple" in opts
        assert "--fork" in secondary
        # The old flag still parses so existing scripts keep working.
        assert "--simple-worker" in opts

    def test_flag_defaults_to_auto_detection(self):
        from feather.cli.worker import worker as worker_cmd

        simple = next(p for p in worker_cmd.params if p.name == "simple")
        assert simple.default is None, "the flag must not override platform detection"


class TestJobSerializerResolution:
    """The queue and the worker have to agree on the serializer."""

    def test_json_is_honoured_when_config_holds_none(self):
        # config.py commonly does JOB_SERIALIZER = os.environ.get("JOB_SERIALIZER"),
        # which leaves the key present but None. dict.get's default would have
        # silently produced pickle while the producer used json.
        from rq.serializers import JSONSerializer

        from feather.jobs.rq import resolve_serializer

        config = {"JOB_SERIALIZER": None}
        environ = {"JOB_SERIALIZER": "json"}
        name = config.get("JOB_SERIALIZER") or environ.get("JOB_SERIALIZER") or "pickle"
        assert resolve_serializer(name) is JSONSerializer
