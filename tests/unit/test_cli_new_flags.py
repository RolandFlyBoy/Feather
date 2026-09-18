"""Unit tests for the flags that let `feather new` run without a terminal.

A server-side agent scaffolds an app from arguments alone, so three things
matter: every prompt has a flag that reaches the options dict the scaffold
manifest consumes, a combination the prompts would never produce fails as a
message rather than as a traceback, and `--json` describes the result in a
shape a caller can read back.

The flags are resolved before anything is written, so these tests never
scaffold a project. What they do to a real project is in
tests/scaffolding/test_cli_new_noninteractive.py.
"""

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from feather.cli.new import new

pytestmark = pytest.mark.unit

# feather/cli/__init__.py binds the `new` *command* as an attribute of the
# feather.cli package, shadowing the submodule of the same name. Reach the
# real module through sys.modules instead.
new_module = sys.modules["feather.cli.new"]

#: No flag given at all: the shape `new()` hands the resolver.
UNANSWERED = {
    "app_type": None,
    "database": None,
    "db_name": None,
    "jobs": None,
    "cache": None,
    "storage": None,
    "email": None,
    "auto_approve_users": None,
    "admin_email": None,
}

#: Every question a single-tenant app asks, answered.
SINGLE_TENANT = {
    "app_type": "single-tenant",
    "database": "postgresql",
    "jobs": True,
    "cache": True,
    "storage": True,
    "email": False,
    "auto_approve_users": False,
    "admin_email": "admin@example.com",
}


def resolve(no_prompt=True, **flags):
    """The options dict the given flags produce, with nothing prompted for."""
    return new_module._resolve_options("shop", {**UNANSWERED, **flags}, no_prompt)


def run(tmp_path, monkeypatch, *args):
    """Invoke `feather new` in an empty directory."""
    monkeypatch.chdir(tmp_path)
    return CliRunner().invoke(new, ["shop", *args], catch_exceptions=False)


# =============================================================================
# Flags reaching the options dict
# =============================================================================


class TestAppType:
    def test_simple_has_no_auth(self):
        options = resolve(app_type="simple")
        assert options["app_type"] == "simple"
        assert options["include_auth"] is False
        assert options["tenant_mode"] is None

    def test_single_tenant(self):
        options = resolve(**SINGLE_TENANT)
        assert options["app_type"] == "single_tenant"
        assert options["include_auth"] is True
        assert options["tenant_mode"] == "single"

    def test_multi_tenant(self):
        options = resolve(**{**SINGLE_TENANT, "app_type": "multi-tenant"})
        assert options["app_type"] == "multi_tenant"
        assert options["tenant_mode"] == "multi"

    def test_multi_tenant_implies_postgresql(self):
        """The only database it can run on, so it needs no --database."""
        options = resolve(**{**SINGLE_TENANT, "app_type": "multi-tenant", "database": None})
        assert options["database"] == "postgresql"
        assert options["db_url"] == "postgresql://localhost/shop"


class TestDatabase:
    def test_none(self):
        options = resolve(app_type="simple", database="none")
        assert options["database"] == "none"
        assert options["db_url"] is None

    def test_sqlite_url_is_settled_when_the_project_is_built(self):
        """`_build_project` fills it in, so the resolver leaves it alone."""
        options = resolve(app_type="simple", database="sqlite")
        assert options["database"] == "sqlite"

    def test_db_name_defaults_to_the_project_name(self):
        options = resolve(app_type="simple", database="postgresql")
        assert options["db_url"] == "postgresql://localhost/shop"

    def test_db_name_flag_is_used(self):
        options = resolve(app_type="simple", database="postgresql", db_name="shop_prod")
        assert options["db_url"] == "postgresql://localhost/shop_prod"


class TestFeatureFlags:
    def test_jobs_without_auth(self):
        assert resolve(app_type="simple", jobs=True)["include_jobs"] is True
        assert resolve(app_type="simple", jobs=False)["include_jobs"] is False

    def test_every_auth_feature_on(self):
        options = resolve(**{**SINGLE_TENANT, "email": True, "auto_approve_users": True})
        assert options["include_cache"] is True
        assert options["include_storage"] is True
        assert options["include_email"] is True
        assert options["auto_approve_users"] is True
        # The storage overlay needs a backend, and the prompt picks GCS.
        assert options["storage_backend"] == "gcs"

    def test_every_auth_feature_off(self):
        options = resolve(
            **{**SINGLE_TENANT, "jobs": False, "cache": False, "storage": False}
        )
        assert options["include_jobs"] is False
        assert options["include_cache"] is False
        assert options["include_storage"] is False
        assert options["storage_backend"] is None

    def test_admin_email(self):
        assert resolve(**SINGLE_TENANT)["admin_email"] == "admin@example.com"

    def test_user_fields_are_left_to_the_model(self):
        """Only the prompt asks about them, so a flag-driven app gets them all."""
        assert "user_fields" not in resolve(**SINGLE_TENANT)


class TestDefaults:
    """--no-prompt with nothing else keeps scaffolding the minimal app."""

    def test_simple_app_with_no_database(self):
        options = resolve()
        assert options["app_type"] == "simple"
        assert options["database"] == "none"

    def test_no_optional_features(self):
        options = resolve()
        assert not any(
            options[key]
            for key in ("include_jobs", "include_cache", "include_storage", "include_email")
        )

    def test_single_tenant_defaults_to_sqlite(self):
        options = resolve(app_type="single-tenant", admin_email="a@b.com")
        assert options["database"] == "sqlite"


# =============================================================================
# Running without prompts
# =============================================================================


class TestNonInteractive:
    def test_a_complete_set_of_flags_needs_no_no_prompt(self, capsys):
        """The flags answer everything, so nothing is asked and nothing printed."""
        options = new_module._resolve_options(
            "shop", {**UNANSWERED, **SINGLE_TENANT}, no_prompt=False
        )
        assert options["admin_email"] == "admin@example.com"
        assert capsys.readouterr().out == ""

    def test_one_missing_answer_leaves_a_question_open(self):
        assert new_module._fully_specified({**UNANSWERED, **SINGLE_TENANT}) is True
        assert (
            new_module._fully_specified({**UNANSWERED, **SINGLE_TENANT, "cache": None})
            is False
        )

    def test_a_database_name_is_not_a_question(self):
        """It defaults to the project name, so it never holds up a run."""
        assert new_module._fully_specified({**UNANSWERED, **SINGLE_TENANT}) is True

    def test_multi_tenant_needs_no_database_answer(self):
        flags = {**UNANSWERED, **SINGLE_TENANT, "app_type": "multi-tenant", "database": None}
        assert new_module._fully_specified(flags) is True


# =============================================================================
# Refused combinations
# =============================================================================


class TestValidation:
    """Each one fails with a message naming the flag, never a traceback."""

    def test_multi_tenant_on_sqlite(self, tmp_path, monkeypatch):
        result = run(tmp_path, monkeypatch, "--app-type", "multi-tenant", "--database", "sqlite")
        assert result.exit_code != 0
        assert "--database postgresql" in result.output

    def test_auth_app_without_a_database(self, tmp_path, monkeypatch):
        result = run(tmp_path, monkeypatch, "--app-type", "single-tenant", "--database", "none")
        assert result.exit_code != 0
        assert "--database sqlite" in result.output

    @pytest.mark.parametrize(
        "flag", ["--cache", "--no-cache", "--storage", "--email", "--auto-approve-users"]
    )
    def test_auth_only_flags_on_a_simple_app(self, tmp_path, monkeypatch, flag):
        result = run(tmp_path, monkeypatch, "--app-type", "simple", flag)
        assert result.exit_code != 0
        assert flag in result.output
        assert "--app-type single-tenant" in result.output

    def test_admin_email_on_a_simple_app(self, tmp_path, monkeypatch):
        result = run(tmp_path, monkeypatch, "--app-type", "simple", "--admin-email", "a@b.com")
        assert result.exit_code != 0
        assert "--admin-email" in result.output

    def test_db_name_without_postgresql(self, tmp_path, monkeypatch):
        result = run(tmp_path, monkeypatch, "--database", "sqlite", "--db-name", "shop")
        assert result.exit_code != 0
        assert "--db-name" in result.output

    def test_auth_app_without_an_admin_email(self, tmp_path, monkeypatch):
        result = run(tmp_path, monkeypatch, "--app-type", "single-tenant", "--no-prompt")
        assert result.exit_code != 0
        assert "--admin-email is required" in result.output

    def test_an_existing_directory_is_still_refused(self, tmp_path, monkeypatch):
        (tmp_path / "shop").mkdir()
        result = run(tmp_path, monkeypatch, "--no-prompt")
        assert result.exit_code != 0
        assert "already exists" in result.output


# =============================================================================
# The --json result
# =============================================================================


class TestJsonResult:
    def test_shape(self):
        options = resolve(**SINGLE_TENANT)
        result = new_module._result(Path("/tmp/shop"), "shop", options, migrated=True)
        assert json.loads(json.dumps(result)) == {
            "path": "/tmp/shop",
            "name": "shop",
            "app_type": "single-tenant",
            "database": "postgresql",
            "database_url": "postgresql://localhost/shop",
            "jobs": True,
            "cache": True,
            "storage": True,
            "email": False,
            "auto_approve_users": False,
            "admin_email": "admin@example.com",
            "migration_created": True,
        }

    def test_app_type_is_the_spelling_the_flag_uses(self):
        options = resolve(**{**SINGLE_TENANT, "app_type": "multi-tenant"})
        result = new_module._result(Path("/tmp/shop"), "shop", options, migrated=False)
        assert result["app_type"] == "multi-tenant"
        assert result["migration_created"] is False

    def test_an_app_with_no_database_says_so(self):
        options = resolve()
        result = new_module._result(Path("/tmp/shop"), "shop", options, migrated=False)
        assert result["database"] == "none"
        assert result["database_url"] is None
        assert result["admin_email"] is None
