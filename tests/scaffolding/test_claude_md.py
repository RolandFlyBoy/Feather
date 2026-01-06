"""Tests for CLAUDE.md generation - verifies documentation is contextual to configuration."""

import pytest

pytestmark = pytest.mark.scaffolding


class TestClaudeMdMinimalApp:
    """Test CLAUDE.md for no-database apps."""

    def test_no_database_commands(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "feather db migrate" not in claude_md
        assert "feather db upgrade" not in claude_md

    def test_no_models_in_project_structure(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        # Should not mention models/ directory in project structure
        assert "models/" not in claude_md

    def test_has_critical_rules(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "⚠️ Critical Rules" in claude_md
        assert "Never use inline Tailwind classes" in claude_md

    def test_links_to_full_docs(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Full Documentation" in claude_md
        assert "github.com/RolandFlyBoy/Feather" in claude_md


class TestClaudeMdWithDatabase:
    """Test CLAUDE.md for apps with database."""

    def test_has_database_commands(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "feather db migrate" in claude_md
        assert "feather db upgrade" in claude_md

    def test_has_models_in_project_structure(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "models/" in claude_md

    def test_shows_database_config(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Database: sqlite" in claude_md


class TestClaudeMdNoAuth:
    """Test CLAUDE.md for apps without authentication."""

    def test_no_admin_required_decorator(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        claude_md = (project / "CLAUDE.md").read_text()
        # @admin_required should not appear as it's auth-specific
        assert "@admin_required" not in claude_md

    def test_no_seeds_command(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "python seeds.py" not in claude_md

    def test_no_auth_decorators_section(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "### Auth Decorators" not in claude_md


class TestClaudeMdWithAuth:
    """Test CLAUDE.md for apps with authentication."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/test",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
    }

    def test_has_auth_decorators_section(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "### Auth Decorators" in claude_md

    def test_has_auth_decorators(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "@auth_required" in claude_md
        assert "@admin_required" in claude_md

    def test_includes_seeds_command(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "python seeds.py" in claude_md

    def test_has_google_image_rule(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "referrerpolicy" in claude_md

    def test_shows_auth_config(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Auth: single-tenant" in claude_md


class TestClaudeMdSingleTenant:
    """Test CLAUDE.md for single-tenant apps."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/test",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
    }

    def test_no_tenant_scoping_section(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "### Tenant Scoping" not in claude_md

    def test_no_tenant_isolation_rule(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Never Bypass Tenant Isolation" not in claude_md


class TestClaudeMdMultiTenant:
    """Test CLAUDE.md for multi-tenant apps."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/test",
        "include_auth": True,
        "tenant_mode": "multi",
        "admin_email": "admin@test.com",
    }

    def test_has_tenant_scoping_section(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "### Tenant Scoping" in claude_md

    def test_has_tenant_isolation_rule(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Never Bypass Tenant Isolation" in claude_md

    def test_shows_multi_tenant_config(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Auth: multi-tenant" in claude_md


class TestClaudeMdCriticalRules:
    """Test that Critical Rules section is always present."""

    def test_has_no_inline_styles_rule(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "No Inline Styles or Scripts" in claude_md

    def test_has_no_native_dialogs_rule(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Never Use Native Browser Dialogs" in claude_md
        assert "alert()" in claude_md

    def test_has_no_raw_fetch_rule(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Never Use Raw fetch()" in claude_md
        assert "ApiUtility" in claude_md

    def test_has_progressive_enhancement_rule(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Progressive Enhancement Order" in claude_md

    def test_has_routes_thin_services_fat_rule(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Routes Thin, Services Fat" in claude_md

    def test_has_protect_routes_rule_when_auth_enabled(self, scaffold_project):
        # This rule only appears when auth is enabled
        project = scaffold_project({
            "database": "postgresql",
            "db_url": "postgresql://localhost/test",
            "include_auth": True,
            "tenant_mode": "single",
            "admin_email": "admin@test.com",
        })
        claude_md = (project / "CLAUDE.md").read_text()
        assert "Always Protect Routes" in claude_md
