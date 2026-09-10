"""Email can be enabled without authentication.

Before 0.9.8 the email overlay added `from services.email_service import
EmailService` to `services/__init__.py` whenever email was enabled, but the
module itself was only written when auth was enabled too. Service discovery
imports that package at startup, so `feather new --email` without auth
produced an app that raised ModuleNotFoundError before serving a request.
"""

import py_compile

import pytest

pytestmark = pytest.mark.scaffolding


EMAIL_NO_AUTH = {
    "database": "sqlite",
    "include_auth": False,
    "include_email": True,
}

EMAIL_WITH_AUTH = {
    "database": "postgresql",
    "db_url": "postgresql://localhost/testapp",
    "include_auth": True,
    "tenant_mode": "single",
    "admin_email": "admin@test.com",
    "include_email": True,
}


class TestEmailWithoutAuth:
    def test_email_service_module_is_written(self, scaffold_project):
        project = scaffold_project(EMAIL_NO_AUTH)
        assert (project / "services" / "email_service.py").exists()

    def test_the_import_it_adds_resolves(self, scaffold_project):
        project = scaffold_project(EMAIL_NO_AUTH)
        package = (project / "services" / "__init__.py").read_text()
        assert "email_service" in package, "the overlay no longer adds the import"
        # The import names a module that exists, which is the whole bug.
        assert (project / "services" / "email_service.py").exists()

    def test_generated_service_compiles(self, scaffold_project):
        project = scaffold_project(EMAIL_NO_AUTH)
        py_compile.compile(
            str(project / "services" / "email_service.py"), doraise=True
        )

    def test_admin_email_tool_stays_behind_auth(self, scaffold_project):
        """The service is generally useful; the admin tool needs the panel."""
        project = scaffold_project(EMAIL_NO_AUTH)
        assert not (project / "templates" / "pages" / "admin" / "tools.html").exists()


class TestEmailWithAuth:
    def test_service_and_admin_tool_both_present(self, scaffold_project):
        project = scaffold_project(EMAIL_WITH_AUTH)
        assert (project / "services" / "email_service.py").exists()
        assert (project / "templates" / "pages" / "admin" / "tools.html").exists()


class TestNoEmail:
    def test_service_absent_when_email_is_off(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        assert not (project / "services" / "email_service.py").exists()
