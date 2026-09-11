"""`feather test` runs the project's own interpreter, not a bare `pytest`.

A bare `pytest` on PATH is whichever one comes first. Running `feather test`
inside app A from a shell with app B's virtualenv active ran B's pytest
against A's tests, which failed on imports that have nothing to do with the
app being tested. The error names a missing third-party package, so it reads
as the app's problem rather than the runner's.
"""

import sys
from pathlib import Path

from feather.cli.dx import _project_python


class TestProjectPython:
    def test_prefers_venv(self, tmp_path):
        python = tmp_path / "venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.touch()
        assert _project_python(tmp_path) == str(python)

    def test_accepts_dot_venv(self, tmp_path):
        python = tmp_path / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.touch()
        assert _project_python(tmp_path) == str(python)

    def test_venv_wins_over_dot_venv(self, tmp_path):
        for name in ("venv", ".venv"):
            p = tmp_path / name / "bin" / "python"
            p.parent.mkdir(parents=True)
            p.touch()
        assert _project_python(tmp_path) == str(tmp_path / "venv" / "bin" / "python")

    def test_falls_back_to_current_interpreter(self, tmp_path):
        assert _project_python(tmp_path) == sys.executable

    def test_ignores_a_venv_directory_with_no_interpreter(self, tmp_path):
        (tmp_path / "venv" / "bin").mkdir(parents=True)
        assert _project_python(tmp_path) == sys.executable


class TestInvocation:
    """The command must go through `-m pytest`, never a bare name."""

    def test_source_uses_dash_m(self):
        source = Path(__file__).parent.parent.parent / "feather/cli/dx.py"
        text = source.read_text()
        assert '_project_python(), "-m", "pytest"' in text
        assert 'cmd = ["pytest", path]' not in text
