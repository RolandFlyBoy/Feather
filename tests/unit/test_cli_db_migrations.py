"""A project must carry its migrations, or it deploys an empty database.

`feather new` leaves migrations/versions empty and git does not track an empty
directory, so nothing used to notice until the app was live with no tables:
`flask db upgrade` applied nothing and said "Migrations applied!". Now the
scaffold writes the first migration, `feather db upgrade` refuses to run
without one, and `feather security-check` fails on it.
"""

from pathlib import Path

from click.testing import CliRunner

from feather.cli.db import db_group, migration_files
from feather.cli.security_check import FAIL, PASS, SKIP, check_migrations


def _project(tmp_path: Path, *, versions: bool = True) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "app.py").write_text("app = None\n")
    if versions:
        (tmp_path / "migrations" / "versions").mkdir(parents=True)
        (tmp_path / "migrations" / "versions" / "__init__.py").write_text("")
    return tmp_path


def _migration(project: Path, name: str = "a1b2c3_initial.py") -> Path:
    path = project / "migrations" / "versions" / name
    path.write_text("revision = 'a1b2c3'\n")
    return path


def test_only_real_migrations_count(tmp_path):
    project = _project(tmp_path)
    assert migration_files(project) == []
    path = _migration(project)
    assert migration_files(project) == [path]


def test_no_migrations_directory_is_not_a_missing_migration(tmp_path):
    assert migration_files(_project(tmp_path, versions=False)) == []


def test_upgrade_refuses_to_run_with_nothing_to_apply(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    result = CliRunner().invoke(db_group, ["upgrade"])
    assert result.exit_code == 1
    assert "No migrations found" in result.output and 'feather db migrate -m "Initial migration"' in result.output
    assert "Applying migrations" not in result.output


def test_upgrade_runs_once_a_migration_exists(tmp_path, monkeypatch):
    project = _project(tmp_path)
    _migration(project)
    monkeypatch.chdir(project)
    ran = []
    monkeypatch.setattr("feather.cli.db._run_streaming", lambda cmd, msg: ran.append(cmd) or 0)
    result = CliRunner().invoke(db_group, ["upgrade"])
    assert result.exit_code == 0 and ran and ran[0][-2:] == ["db", "upgrade"]


def test_security_check_fails_on_an_empty_migrations_directory(tmp_path):
    project = _project(tmp_path)
    check = check_migrations(project)
    assert check.status == FAIL and "no migrations" in check.message
    assert "feather db migrate" in check.remedy
    _migration(project)
    assert check_migrations(project).status == PASS
    assert check_migrations(_project(tmp_path / "other", versions=False)).status == SKIP
