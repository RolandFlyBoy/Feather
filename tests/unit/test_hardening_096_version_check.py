"""0.9.6: `feather --version` and `feather new` warn when a newer release is on PyPI."""

import click
import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.unit


@pytest.fixture
def stub_new(monkeypatch):
    """Replace the real `new` command so the group callback runs without scaffolding."""
    from feather.cli import cli

    monkeypatch.setitem(cli.commands, "new", click.Command("new", callback=lambda: click.echo("stub new")))
    return cli


@pytest.fixture(autouse=True)
def allow_update_check(monkeypatch):
    monkeypatch.delenv("FEATHER_NO_UPDATE_CHECK", raising=False)


class TestVersionDriftWarning:
    def test_version_prints_notice_when_outdated(self, monkeypatch):
        import feather.cli as cli_module

        monkeypatch.setattr(cli_module, "_fetch_latest_version", lambda: "99.0.0")
        result = CliRunner().invoke(cli_module.cli, ["--version"])

        assert result.exit_code == 0
        assert cli_module.__version__ in result.output
        assert "99.0.0" in result.output
        assert "pip install" in result.output

    def test_version_silent_when_current(self, monkeypatch):
        import feather.cli as cli_module

        monkeypatch.setattr(cli_module, "_fetch_latest_version", lambda: cli_module.__version__)
        result = CliRunner().invoke(cli_module.cli, ["--version"])

        assert result.exit_code == 0
        assert cli_module.__version__ in result.output
        assert "newer" not in result.output.lower()

    def test_version_silent_when_pypi_ahead_is_older(self, monkeypatch):
        """A local dev build ahead of PyPI must not be told to downgrade."""
        import feather.cli as cli_module

        monkeypatch.setattr(cli_module, "_fetch_latest_version", lambda: "0.0.1")
        result = CliRunner().invoke(cli_module.cli, ["--version"])
        assert "newer" not in result.output.lower()

    def test_offline_never_fails(self, monkeypatch):
        import feather.cli as cli_module

        def boom():
            raise OSError("no network")

        monkeypatch.setattr(cli_module, "_fetch_latest_version", boom)
        result = CliRunner().invoke(cli_module.cli, ["--version"])

        assert result.exit_code == 0
        assert cli_module.__version__ in result.output

    def test_env_var_skips_check(self, monkeypatch):
        import feather.cli as cli_module

        called = []
        monkeypatch.setenv("FEATHER_NO_UPDATE_CHECK", "1")
        monkeypatch.setattr(cli_module, "_fetch_latest_version", lambda: called.append(1) or "99.0.0")
        result = CliRunner().invoke(cli_module.cli, ["--version"])

        assert result.exit_code == 0
        assert called == []
        assert "99.0.0" not in result.output

    def test_new_command_prints_notice(self, monkeypatch, stub_new):
        import feather.cli as cli_module

        monkeypatch.setattr(cli_module, "_fetch_latest_version", lambda: "99.0.0")
        result = CliRunner().invoke(stub_new, ["new"])

        assert result.exit_code == 0, result.output
        assert "stub new" in result.output
        assert "99.0.0" in result.output

    def test_other_commands_do_not_check(self, monkeypatch):
        import feather.cli as cli_module

        called = []
        monkeypatch.setattr(cli_module, "_fetch_latest_version", lambda: called.append(1) or "99.0.0")
        monkeypatch.setitem(cli_module.cli.commands, "routes", click.Command("routes", callback=lambda: None))
        CliRunner().invoke(cli_module.cli, ["routes"])
        assert called == []

    def test_fetch_uses_pypi_json_with_timeout(self, monkeypatch):
        """The real fetcher hits the PyPI JSON API with a short timeout."""
        import io
        import json
        import feather.cli as cli_module

        seen = {}

        def fake_urlopen(url, timeout=None):
            seen["url"] = url
            seen["timeout"] = timeout
            return io.BytesIO(json.dumps({"info": {"version": "1.2.3"}}).encode())

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        assert cli_module._fetch_latest_version() == "1.2.3"
        assert seen["url"] == "https://pypi.org/pypi/feather-framework/json"
        assert seen["timeout"] is not None and seen["timeout"] <= 2
