"""`feather jobs run NAME`: run one @job now, for cron-style schedulers."""

import pytest
from click.testing import CliRunner
from flask import current_app

from feather.cli.jobs import jobs
from feather.jobs import find_job, job, registered_jobs

pytestmark = pytest.mark.unit

CALLS = []


@job
def cli_run_record(*args, **kwargs):
    CALLS.append((args, kwargs, current_app.name))
    return {"args": list(args), "kwargs": kwargs}


@job(retry=3)
def cli_run_explode():
    raise RuntimeError("disk full")


def cli_run_not_a_job():
    return None


@pytest.fixture
def app(monkeypatch):
    from feather import Feather

    app = Feather("jobs_run_app")
    app.config["TESTING"] = True
    import feather.cli  # noqa: F401 - `feather.cli.worker` is shadowed by the command
    import sys

    monkeypatch.setattr(sys.modules["feather.cli.worker"], "_get_app", lambda: app)
    CALLS.clear()
    return app


def invoke(*args):
    return CliRunner().invoke(jobs, ["run", *args])


class TestFindJob:
    def test_registry_has_dotted_paths(self):
        assert registered_jobs()[f"{__name__}.cli_run_record"] is cli_run_record

    def test_by_name_suffix_and_dotted_path(self):
        assert find_job("cli_run_record") is cli_run_record
        assert find_job(f"{__name__.rsplit('.', 1)[1]}.cli_run_record") is cli_run_record
        assert find_job(f"{__name__}.cli_run_record") is cli_run_record

    def test_unknown_name(self):
        with pytest.raises(LookupError, match="No job named 'nope'"):
            find_job("nope")

    def test_dotted_path_to_a_plain_function(self):
        with pytest.raises(LookupError, match="not decorated with @job"):
            find_job(f"{__name__}.cli_run_not_a_job")

    def test_ambiguous_name(self, monkeypatch):
        import feather.jobs as jobs_module

        monkeypatch.setitem(jobs_module._JOB_REGISTRY, "other.module.cli_run_record", object())
        with pytest.raises(LookupError, match="more than one job"):
            find_job("cli_run_record")


class TestJobsRun:
    def test_runs_synchronously_in_the_app_context(self, app):
        result = invoke("cli_run_record")
        assert result.exit_code == 0, result.output
        assert CALLS == [((), {}, "jobs_run_app")]
        assert result.output.startswith(f"Job {__name__}.cli_run_record finished in ")
        assert result.output.count("\n") == 1

    def test_passes_args_and_kwargs_json_decoded(self, app):
        result = invoke("cli_run_record", "--arg", "weekly", "--arg", "30",
                        "--kwarg", "dry_run=true", "--kwarg", "code=007",
                        "--kwarg", "ids=[1, 2]")
        assert result.exit_code == 0, result.output
        assert CALLS[0][0] == ("weekly", 30)
        assert CALLS[0][1] == {"dry_run": True, "code": "007", "ids": [1, 2]}
        assert "'kwargs': {" in result.output

    def test_bad_kwarg(self, app):
        result = invoke("cli_run_record", "--kwarg", "novalue")
        assert result.exit_code == 2
        assert "KEY=VALUE" in result.output
        assert CALLS == []

    def test_failure_exits_non_zero_and_runs_once(self, app):
        result = invoke("cli_run_explode")
        assert result.exit_code == 1
        assert "RuntimeError: disk full" in result.output
        assert result.output.count("Traceback") == 1
        assert f"Job {__name__}.cli_run_explode failed after" in result.output

    def test_unknown_job_exits_2(self, app):
        result = invoke("does_not_exist")
        assert result.exit_code == 2
        assert "No job named 'does_not_exist'" in result.output

    def test_bypasses_the_queue(self, app, monkeypatch):
        """Even with rq configured nothing is enqueued."""
        import feather.jobs as jobs_module

        def boom():
            raise AssertionError("get_queue must not be called")

        monkeypatch.setattr(jobs_module, "get_queue", boom)
        app.config["JOB_BACKEND"] = "rq"
        result = invoke("cli_run_record")
        assert result.exit_code == 0, result.output
