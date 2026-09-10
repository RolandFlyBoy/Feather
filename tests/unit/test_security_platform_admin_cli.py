"""Security: ``feather platform-admin`` must not interpolate the email into code."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.unit

TRICKY_EMAIL = 'x"); import os; os.system("id"); print("@example.com'


def _run(email, *extra):
    from feather.cli.platform_admin import platform_admin

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("app.py", "w") as fh:
            fh.write("app = None\n")
        with patch("feather.cli.platform_admin.subprocess.run") as run:
            run.return_value.stdout = f"SUCCESS: Granted platform admin to {email}\n"
            run.return_value.stderr = ""
            result = runner.invoke(platform_admin, [email, *extra])
    return result, run


def test_email_is_never_part_of_the_executed_source():
    result, run = _run(TRICKY_EMAIL)

    assert result.exit_code == 0, result.output
    argv = run.call_args.args[0]
    source = " ".join(argv)
    assert TRICKY_EMAIL not in source
    assert "os.system" not in source


def test_email_and_action_reach_the_child_through_the_environment():
    _, run = _run(TRICKY_EMAIL, "--revoke")

    env = run.call_args.kwargs["env"]
    assert env["FEATHER_PLATFORM_ADMIN_EMAIL"] == TRICKY_EMAIL
    assert env["FEATHER_PLATFORM_ADMIN_ACTION"] == "revoke"

    _, run = _run("a@example.com")
    assert run.call_args.kwargs["env"]["FEATHER_PLATFORM_ADMIN_ACTION"] == "grant"


def test_success_and_error_output_are_unchanged():
    result, _ = _run("a@example.com")
    assert result.exit_code == 0
    assert "Granted platform admin to a@example.com" in result.output

    from feather.cli.platform_admin import platform_admin

    runner = CliRunner()
    with runner.isolated_filesystem():
        open("app.py", "w").write("app = None\n")
        with patch("feather.cli.platform_admin.subprocess.run") as run:
            run.return_value.stdout = "ERROR: User 'a@example.com' not found\n"
            run.return_value.stderr = ""
            result = runner.invoke(platform_admin, ["a@example.com"])
    assert result.exit_code != 0
    assert "User 'a@example.com' not found" in result.output


def test_child_script_reads_email_from_environment():
    """Run the real child script against a fake ``app`` module."""
    import os
    import subprocess
    import sys
    import textwrap

    import importlib

    # feather.cli rebinds the name to the click Command, so import the
    # module object explicitly.
    mod = importlib.import_module("feather.cli.platform_admin")

    runner = CliRunner()
    with runner.isolated_filesystem():
        # A fake project: `app` exposes a User "model" whose query returns
        # a record only for the tricky email, and a stand-in feather.db.
        with open("app.py", "w") as fh:
            fh.write(textwrap.dedent('''
                import sys, types
                class _Session:
                    def commit(self): print("COMMITTED")
                class _Record:
                    is_platform_admin = False
                class _Query:
                    def __init__(self): self.kw = {}
                    def filter_by(self, **kw): self.kw = kw; return self
                    def first(self):
                        import os
                        return _Record() if self.kw.get("email") == os.environ["EXPECTED"] else None
                class User:
                    query = _Query()
                class _Model:
                    @staticmethod
                    def __subclasses__(): return [User]
                db = types.SimpleNamespace(Model=_Model, session=_Session())
                fake = types.ModuleType("feather.db"); fake.db = db
                pkg = types.ModuleType("feather"); pkg.db = fake
                sys.modules["feather"] = pkg
                sys.modules["feather.db"] = fake
                app = object()
            '''))
        env = {
            **os.environ,
            "EXPECTED": TRICKY_EMAIL,
            "FEATHER_PLATFORM_ADMIN_EMAIL": TRICKY_EMAIL,
            "FEATHER_PLATFORM_ADMIN_ACTION": "grant",
            "PYTHONPATH": os.getcwd(),
        }
        proc = subprocess.run(
            [sys.executable, "-c", mod._child_source()],
            capture_output=True, text=True, env=env, cwd=os.getcwd(),
        )
    assert proc.returncode == 0, proc.stderr
    assert "COMMITTED" in proc.stdout
    assert f"SUCCESS: Granted platform admin to {TRICKY_EMAIL}" in proc.stdout
