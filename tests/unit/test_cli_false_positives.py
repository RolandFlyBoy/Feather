"""Three CLI reports that told an app the wrong thing.

All three were found upgrading the two production apps to 0.9.9. Each one
either failed a command on correct code or, worse, reported a security state
that was not the one being asked about. A checker people stop believing is
of no use, so these are regression tests rather than tidying.
"""

import os
from pathlib import Path

import pytest

from feather.cli.check import SCRIPT_BLOCK_RE
from feather.cli.security_check import load_env_settings


class TestJsonDataIslandsAreNotInlineScripts:
    """`<script type="application/json">` carries data, not code."""

    @pytest.mark.parametrize(
        "markup",
        [
            '<script type="application/json" id="d">{"a":1}</script>',
            "<script type='application/json'>{}</script>",
            '<script type="application/ld+json">{}</script>',
            '<script type="importmap">{}</script>',
            '<script type="text/template"><div></div></script>',
            '<script src="/static/app.js"></script>',
        ],
    )
    def test_not_flagged(self, markup):
        assert SCRIPT_BLOCK_RE.search(markup) is None

    @pytest.mark.parametrize(
        "markup",
        [
            "<script>alert(1)</script>",
            '<script type="text/javascript">go()</script>',
            '<script type="module">import "./a.js"</script>',
            "<script >x()</script>",
        ],
    )
    def test_still_flagged(self, markup):
        assert SCRIPT_BLOCK_RE.search(markup) is not None


class TestNamedEnvFileWins:
    """`--env-file X` must report on X, not on an ambient .env.

    Importing anything under feather.cli loads the project's .env into
    os.environ as a side effect. Before the fix that ambient copy overrode
    the named file, so checking production from a developer's checkout
    reported the development SECRET_KEY as production's.
    """

    @staticmethod
    def _write(path, **values):
        path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")

    def test_named_file_beats_process_environment(self, tmp_path, monkeypatch):
        prod = tmp_path / "prod.env"
        self._write(prod, SECRET_KEY="p" * 64, FLASK_DEBUG="0")
        monkeypatch.setenv("SECRET_KEY", "dev-secret-key-change-in-production")
        monkeypatch.setenv("FLASK_DEBUG", "1")

        settings = load_env_settings(tmp_path, "prod.env", [])

        assert settings.get("SECRET_KEY") == "p" * 64
        assert settings.get("FLASK_DEBUG") == "0"

    def test_process_environment_still_fills_keys_the_file_omits(
        self, tmp_path, monkeypatch
    ):
        prod = tmp_path / "prod.env"
        self._write(prod, SECRET_KEY="p" * 64)
        monkeypatch.setenv("REDIS_URL", "redis://from-env:6379/0")

        settings = load_env_settings(tmp_path, "prod.env", [])

        assert settings.get("SECRET_KEY") == "p" * 64
        assert settings.get("REDIS_URL") == "redis://from-env:6379/0"

    def test_without_a_named_file_the_environment_still_wins(
        self, tmp_path, monkeypatch
    ):
        self._write(tmp_path / ".env", SECRET_KEY="from-file")
        monkeypatch.setenv("SECRET_KEY", "from-environment")

        settings = load_env_settings(tmp_path, None, [])

        assert settings.get("SECRET_KEY") == "from-environment"

    def test_says_which_file_was_authoritative(self, tmp_path):
        self._write(tmp_path / "prod.env", SECRET_KEY="p" * 64)
        notes = []

        load_env_settings(tmp_path, "prod.env", notes)

        assert any("authoritative" in n for n in notes)


class TestEnvCheckGuidance:
    """Missing-key output has to say how to declare a key legitimately unset."""

    def test_names_the_explicit_default_form(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from feather.cli.env import env_group

        (tmp_path / "config.py").write_text(
            "import os\n"
            "class Config:\n"
            "    ROTATION_KEY = os.environ.get('ENCRYPTION_KEY_PREVIOUS')\n"
        )
        (tmp_path / ".env").write_text("")
        monkeypatch.delenv("ENCRYPTION_KEY_PREVIOUS", raising=False)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(env_group, ["check"])

        assert result.exit_code == 1, result.output
        assert "ENCRYPTION_KEY_PREVIOUS" in result.output
        assert 'os.environ.get("KEY", None)' in result.output

    def test_no_guidance_when_nothing_is_missing(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from feather.cli.env import env_group

        (tmp_path / "config.py").write_text(
            "import os\n"
            "class Config:\n"
            "    THING = os.environ.get('SOME_OPTIONAL_THING', 'default')\n"
        )
        (tmp_path / ".env").write_text("")
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(env_group, ["check"])

        assert result.exit_code == 0, result.output
        assert 'os.environ.get("KEY", None)' not in result.output
