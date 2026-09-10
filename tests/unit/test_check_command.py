"""Tests for `feather check`, the convention linter.

Each test writes a tiny project into tmp_path and asserts which rules fire.
The point of the command is that the rules in a scaffolded app's CLAUDE.md
become machine-checkable, so the tests are written rule by rule.
"""

import json

import pytest
from click.testing import CliRunner

from feather.cli.check import check, run_checks

pytestmark = pytest.mark.unit


def make_project(root, files):
    """Write {relative path: content} and the app.py that marks a project."""
    (root / "app.py").write_text("from feather import Feather\napp = Feather(__name__)\n")
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


def rules(root, only=None):
    """Rule names reported for a project, as a list (duplicates preserved)."""
    return [f.rule for f in run_checks(root, only)]


def run_cli(root, *args):
    return CliRunner().invoke(check, ["--path", str(root), *args], catch_exceptions=False)


# =============================================================================
# Templates
# =============================================================================


class TestTemplateRules:
    def test_inline_script_is_reported(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": "<script>doThing()</script>"})
        assert "inline-script" in rules(tmp_path)

    def test_script_with_src_is_allowed(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<script src="/static/js/app.js"></script>'})
        assert "inline-script" not in rules(tmp_path)

    def test_inline_event_handler_is_reported(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<button onclick="go()">x</button>'})
        assert "inline-handler" in rules(tmp_path)

    def test_htmx_attributes_are_allowed(self, tmp_path):
        make_project(
            tmp_path,
            {"templates/a.html": '<button hx-post="/like" hx-target="#x">Like</button>'},
        )
        assert rules(tmp_path, "templates") == []

    def test_inline_tailwind_is_reported(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<div class="px-4 bg-blue-600">x</div>'})
        assert "inline-tailwind" in rules(tmp_path)

    def test_semantic_class_names_are_allowed(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<div class="card card-elevated">x</div>'})
        assert "inline-tailwind" not in rules(tmp_path)

    def test_style_attribute_is_reported(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<div style="color:red">x</div>'})
        assert "inline-style" in rules(tmp_path)

    def test_google_image_without_referrerpolicy_is_reported(self, tmp_path):
        make_project(
            tmp_path,
            {"templates/a.html": '<img src="https://lh3.googleusercontent.com/a/x">'},
        )
        assert "google-image-referrer" in rules(tmp_path)

    def test_google_image_with_referrerpolicy_is_allowed(self, tmp_path):
        make_project(
            tmp_path,
            {
                "templates/a.html": '<img src="https://lh3.googleusercontent.com/a/x" '
                'referrerpolicy="no-referrer">'
            },
        )
        assert "google-image-referrer" not in rules(tmp_path)

    def test_other_images_are_not_flagged(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<img src="/static/logo.png">'})
        assert "google-image-referrer" not in rules(tmp_path)

    def test_line_numbers_point_at_the_problem(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": "<div>ok</div>\n\n<script>x()</script>"})
        finding = run_checks(tmp_path, "templates")[0]
        assert finding.line == 3


# =============================================================================
# JavaScript
# =============================================================================


class TestJavaScriptRules:
    @pytest.mark.parametrize("call", ["alert('x')", "confirm('x')", "prompt('x')"])
    def test_native_dialogs_are_reported(self, tmp_path, call):
        make_project(tmp_path, {"static/js/app.js": f"function f() {{ {call}; }}"})
        assert "native-dialog" in rules(tmp_path)

    def test_dialog_in_a_comment_is_ignored(self, tmp_path):
        make_project(tmp_path, {"static/js/app.js": "// never use confirm('x')\nlet a = 1;"})
        assert "native-dialog" not in rules(tmp_path)

    def test_dialog_in_a_string_is_ignored(self, tmp_path):
        make_project(tmp_path, {"static/js/app.js": "const help = 'call confirm(y) here';"})
        assert "native-dialog" not in rules(tmp_path)

    def test_dialog_in_a_block_comment_is_ignored(self, tmp_path):
        make_project(tmp_path, {"static/js/app.js": "/*\n alert('x')\n*/\nlet a = 1;"})
        assert "native-dialog" not in rules(tmp_path)

    def test_method_named_confirm_is_ignored(self, tmp_path):
        make_project(tmp_path, {"static/js/app.js": "modal.confirm('are you sure');"})
        assert "native-dialog" not in rules(tmp_path)

    def test_raw_fetch_is_reported(self, tmp_path):
        make_project(tmp_path, {"static/js/app.js": "fetch('/api/x').then(r => r.json());"})
        assert "raw-fetch" in rules(tmp_path)

    def test_api_utility_is_allowed(self, tmp_path):
        make_project(tmp_path, {"static/js/app.js": "await ApiUtility.get('/api/x');"})
        assert "raw-fetch" not in rules(tmp_path)

    def test_islands_are_checked_too(self, tmp_path):
        make_project(tmp_path, {"static/islands/counter.js": "fetch('/api/count');"})
        assert "raw-fetch" in rules(tmp_path)


# =============================================================================
# Routes
# =============================================================================


ROUTE_HEADER = "from feather import page, api, auth_required\n\n"


class TestRouteRules:
    def test_route_without_auth_decorator_warns(self, tmp_path):
        make_project(
            tmp_path,
            {"routes/pages/x.py": ROUTE_HEADER + "@page.get('/x')\ndef x():\n    return 'x'\n"},
        )
        findings = run_checks(tmp_path, "routes")
        assert [f.rule for f in findings] == ["unprotected-route"]
        assert findings[0].severity == "warning"

    def test_route_with_auth_decorator_passes(self, tmp_path):
        make_project(
            tmp_path,
            {
                "routes/pages/x.py": ROUTE_HEADER
                + "@page.get('/x')\n@auth_required\ndef x():\n    return 'x'\n"
            },
        )
        assert rules(tmp_path, "routes") == []

    def test_module_marked_public_is_exempt(self, tmp_path):
        make_project(
            tmp_path,
            {
                "routes/pages/x.py": "# feather: public\n"
                + ROUTE_HEADER
                + "@page.get('/x')\ndef x():\n    return 'x'\n"
            },
        )
        assert rules(tmp_path, "routes") == []

    def test_fat_route_warns(self, tmp_path):
        body = "\n".join(f"    v{i} = {i}" for i in range(20))
        make_project(
            tmp_path,
            {
                "routes/pages/x.py": ROUTE_HEADER
                + f"@page.get('/x')\n@auth_required\ndef x():\n{body}\n    return 'x'\n"
            },
        )
        assert "fat-route" in rules(tmp_path, "routes")

    def test_non_route_function_is_ignored(self, tmp_path):
        make_project(tmp_path, {"routes/pages/x.py": "def helper():\n    return 1\n"})
        assert rules(tmp_path, "routes") == []

    def test_syntax_error_is_reported(self, tmp_path):
        make_project(tmp_path, {"routes/pages/x.py": "def broken(\n"})
        assert "syntax-error" in rules(tmp_path)


# =============================================================================
# Tenant isolation
# =============================================================================


MODEL = (
    "from feather.db import db, Model\n"
    "from feather.db.mixins import TenantScopedMixin\n\n"
    "class Doc(TenantScopedMixin, Model):\n"
    "    __tablename__ = 'docs'\n"
)


class TestTenantIsolation:
    def test_unfiltered_query_on_scoped_model_is_reported(self, tmp_path):
        make_project(
            tmp_path,
            {
                "models/doc.py": MODEL,
                "services/doc_service.py": "from models import Doc\n\n"
                "def all_docs():\n    return Doc.query.all()\n",
            },
        )
        assert "tenant-isolation" in rules(tmp_path)

    def test_query_mentioning_tenant_is_allowed(self, tmp_path):
        make_project(
            tmp_path,
            {
                "models/doc.py": MODEL,
                "services/doc_service.py": "from models import Doc\n"
                "from feather.auth import get_current_tenant_id\n\n"
                "def all_docs():\n"
                "    return Doc.for_tenant(get_current_tenant_id()).all()\n",
            },
        )
        assert "tenant-isolation" not in rules(tmp_path)

    def test_unscoped_model_is_not_checked(self, tmp_path):
        make_project(
            tmp_path,
            {
                "models/doc.py": "from feather.db import db, Model\n\n"
                "class Doc(Model):\n    __tablename__ = 'docs'\n",
                "services/doc_service.py": "from models import Doc\n\n"
                "def all_docs():\n    return Doc.query.all()\n",
            },
        )
        assert "tenant-isolation" not in rules(tmp_path)


# =============================================================================
# Islands
# =============================================================================


class TestIslands:
    def test_orphan_island_warns(self, tmp_path):
        make_project(
            tmp_path,
            {"static/islands/counter.js": "island('counter', {});", "templates/a.html": "<div></div>"},
        )
        findings = run_checks(tmp_path, "islands")
        assert [f.rule for f in findings] == ["orphan-island"]
        assert findings[0].severity == "warning"

    def test_mounted_island_passes(self, tmp_path):
        make_project(
            tmp_path,
            {
                "static/islands/counter.js": "island('counter', {});",
                "templates/a.html": '<div data-island="counter"></div>',
            },
        )
        assert rules(tmp_path, "islands") == []

    def test_missing_island_is_an_error(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<div data-island="ghost"></div>'})
        findings = run_checks(tmp_path, "islands")
        assert [f.rule for f in findings] == ["missing-island"]
        assert findings[0].severity == "error"


# =============================================================================
# CLI behaviour
# =============================================================================


class TestCli:
    def test_clean_project_exits_zero(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<div class="card">ok</div>'})
        result = run_cli(tmp_path)
        assert result.exit_code == 0
        assert "No problems found" in result.output

    def test_error_exits_one(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": "<script>x()</script>"})
        assert run_cli(tmp_path).exit_code == 1

    def test_warning_alone_exits_zero(self, tmp_path):
        make_project(
            tmp_path,
            {"routes/pages/x.py": ROUTE_HEADER + "@page.get('/x')\ndef x():\n    return 'x'\n"},
        )
        assert run_cli(tmp_path).exit_code == 0

    def test_strict_makes_warnings_fail(self, tmp_path):
        make_project(
            tmp_path,
            {"routes/pages/x.py": ROUTE_HEADER + "@page.get('/x')\ndef x():\n    return 'x'\n"},
        )
        assert run_cli(tmp_path, "--strict").exit_code == 1

    def test_json_output_is_machine_readable(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": "<script>x()</script>"})
        result = run_cli(tmp_path, "--json")
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["counts"]["error"] == 1
        finding = payload["findings"][0]
        assert finding["file"] == "templates/a.html"
        assert finding["rule"] == "inline-script"
        assert finding["remedy"]

    def test_only_runs_one_group(self, tmp_path):
        make_project(
            tmp_path,
            {
                "templates/a.html": "<script>x()</script>",
                "static/js/app.js": "fetch('/x');",
            },
        )
        payload = json.loads(run_cli(tmp_path, "--only", "javascript", "--json").output)
        assert {f["rule"] for f in payload["findings"]} == {"raw-fetch"}

    def test_non_project_directory_is_rejected(self, tmp_path):
        result = CliRunner().invoke(check, ["--path", str(tmp_path)])
        assert result.exit_code != 0
        assert "Not a Feather project" in result.output

    def test_vendor_directories_are_skipped(self, tmp_path):
        make_project(tmp_path, {"templates/a.html": '<div class="card">ok</div>'})
        vendored = tmp_path / "node_modules" / "pkg" / "templates"
        vendored.mkdir(parents=True)
        (vendored / "bad.html").write_text("<script>x()</script>")
        assert rules(tmp_path) == []
