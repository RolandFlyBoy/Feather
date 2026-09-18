"""`feather new --files-only`: the project's files and nothing else.

What must not regress: a caller that scaffolds on one machine and installs on
another gets the files without a database, git repository, virtualenv, npm
install or migration being attempted where they are written; it can scaffold
into a fresh clone that holds only `.git`; and it can never write over a
directory that already holds someone's work.
"""

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from feather.cli.new import new

FLAGS = [
    "--app-type", "single-tenant", "--database", "postgresql",
    "--jobs", "--cache", "--no-storage", "--no-email", "--no-auto-approve-users",
    "--admin-email", "admin@example.com", "--json", "--files-only",
]


def _run(cwd: Path, name: str, *extra):
    runner = CliRunner()
    import os

    old = os.getcwd()
    os.chdir(cwd)
    try:
        return runner.invoke(new, [name, *extra])
    finally:
        os.chdir(old)


def test_files_only_writes_the_project_and_touches_nothing_else(tmp_path, monkeypatch):
    import sys

    # feather.cli exports the command as `new`, which shadows the module of
    # the same name, so patch the module object itself.
    module = sys.modules["feather.cli.new"]
    calls = []
    for step in ("_create_database", "_init_git", "_install_dependencies", "_setup_venv", "_create_initial_migration"):
        monkeypatch.setattr(module, step, lambda *a, _s=step, **k: calls.append(_s) or True)

    result = _run(tmp_path, "shop", *FLAGS)
    assert result.exit_code == 0, result.output
    project = tmp_path / "shop"
    for expected in ("app.py", "config.py", "Dockerfile", "requirements.txt", "AGENTS.md", "migrations"):
        assert (project / expected).exists(), expected
    assert not (project / "venv").exists() and not (project / "node_modules").exists()
    assert calls == []  # no database, git, npm, venv or migration was attempted


def test_files_only_still_reports_json(tmp_path):
    result = _run(tmp_path, "shop", *FLAGS)
    body = json.loads(result.output.strip().splitlines()[-1])
    assert body["name"] == "shop" and body["database"] == "postgresql"
    assert body["migration_created"] is False


def test_a_fresh_clone_can_be_scaffolded_into(tmp_path):
    clone = tmp_path / "app"
    clone.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
    result = _run(clone, ".", *FLAGS)
    assert result.exit_code == 0, result.output
    assert (clone / "app.py").exists() and (clone / ".git").exists()
    assert json.loads(result.output.strip().splitlines()[-1])["name"] == "app"


def test_a_directory_with_real_files_is_never_written_over(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "notes.txt").write_text("mine")
    result = _run(work, ".", *FLAGS)
    assert result.exit_code != 0 and "already exists" in result.output
    assert (work / "notes.txt").read_text() == "mine"
    assert not (work / "app.py").exists()


def test_without_files_only_an_existing_directory_is_still_refused(tmp_path):
    clone = tmp_path / "app"
    clone.mkdir()
    (clone / ".git").mkdir()
    flags = [f for f in FLAGS if f != "--files-only"]
    result = _run(clone, ".", *flags)
    assert result.exit_code != 0 and "already exists" in result.output
