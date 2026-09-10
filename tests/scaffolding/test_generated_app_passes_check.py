"""A freshly generated app passes `feather check` with no errors.

`feather check` enforces the rules the generated CLAUDE.md states. If the
scaffold itself breaks them, the first thing a developer sees in a new
project is a failing linter, and the natural response is to stop trusting
it. So the scaffold has to hold to its own rules.

Warnings are a different matter and are not asserted here. The generated
templates use Tailwind utilities inline, which `feather check` reports as a
warning precisely because it is a matter of taste rather than a defect.
"""

import pytest

from feather.cli.check import run_checks

pytestmark = pytest.mark.scaffolding


CONFIGS = {
    "simple": {"database": "none"},
    "sqlite": {"database": "sqlite", "db_url": "sqlite:///app.db"},
    "single_tenant": {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
    },
    "multi_tenant": {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "multi",
        "admin_email": "admin@test.com",
        "include_jobs": True,
        "include_cache": True,
    },
}


def errors(project):
    return [f for f in run_checks(project) if f.severity == "error"]


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_no_errors(scaffold_project, name):
    project = scaffold_project(CONFIGS[name])
    found = errors(project)
    assert found == [], "\n".join(
        f"{f.as_dict(project)['file']}:{f.line}  {f.rule}  {f.message}" for f in found
    )


class TestSpecificRules:
    """The rules most likely to creep back into a template."""

    def test_no_inline_styles(self, scaffold_project):
        project = scaffold_project(CONFIGS["multi_tenant"])
        assert [f for f in run_checks(project) if f.rule == "inline-style"] == []

    def test_no_inline_scripts(self, scaffold_project):
        project = scaffold_project(CONFIGS["multi_tenant"])
        assert [f for f in run_checks(project) if f.rule == "inline-script"] == []

    def test_no_inline_event_handlers(self, scaffold_project):
        project = scaffold_project(CONFIGS["multi_tenant"])
        assert [f for f in run_checks(project) if f.rule == "inline-handler"] == []

    def test_no_native_dialogs_or_raw_fetch(self, scaffold_project):
        project = scaffold_project(CONFIGS["multi_tenant"])
        rules = {f.rule for f in run_checks(project)}
        assert "native-dialog" not in rules
        assert "raw-fetch" not in rules

    def test_google_avatars_carry_referrerpolicy(self, scaffold_project):
        project = scaffold_project(CONFIGS["multi_tenant"])
        assert [
            f for f in run_checks(project) if f.rule == "google-image-referrer"
        ] == []

    def test_every_island_is_mounted(self, scaffold_project):
        project = scaffold_project(CONFIGS["sqlite"])
        assert [f for f in run_checks(project) if f.rule == "missing-island"] == []


class TestChartMarkup:
    """The analytics chart needs real dimensions, from a class not an attribute."""

    def test_chart_canvas_uses_a_class(self, scaffold_project):
        project = scaffold_project(CONFIGS["single_tenant"])
        page = (project / "templates/pages/admin/analytics.html").read_text()
        assert 'class="admin-chart-canvas"' in page
        assert "style=" not in page

    def test_the_class_is_defined_with_dimensions(self, scaffold_project):
        project = scaffold_project(CONFIGS["single_tenant"])
        css = (project / "static/css/app.css").read_text()
        assert ".admin-chart-canvas" in css
        # ECharts measures the element at init; without both it renders 0x0.
        block = css.split(".admin-chart-canvas", 1)[1].split("}", 1)[0]
        assert "width" in block and "height" in block


class TestToastDataCarrier:
    """The pending-toast div carries data, shows nothing, and needs no CSS."""

    def test_uses_the_hidden_attribute(self, scaffold_project):
        project = scaffold_project(CONFIGS["sqlite"])
        base = (project / "templates/base.html").read_text()
        line = next(l for l in base.splitlines() if "pending-toast-data" in l)
        assert " hidden" in line
        assert "style=" not in line
