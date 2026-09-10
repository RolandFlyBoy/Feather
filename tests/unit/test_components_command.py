"""Tests for `feather components`, the component catalogue.

The catalogue is parsed from the macro definitions themselves rather than
maintained by hand, so these tests mostly pin that parsing: signatures with
awkward defaults, several macros in one file, and an app overriding a
framework component.
"""

import json

import pytest
from click.testing import CliRunner

from feather.cli.components import (
    collect,
    components,
    framework_components_dir,
    parse_file,
    to_markdown,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app.py").write_text("app = None\n")
    (tmp_path / "templates" / "components").mkdir(parents=True)
    return tmp_path


def write_component(project, name, body):
    path = project / "templates" / "components" / f"{name}.html"
    path.write_text(body)
    return path


class TestParsing:
    def test_reads_name_and_arguments(self, project):
        path = write_component(project, "x", '{% macro badge(text, tone="info") %}b{% endmacro %}')
        (found,) = parse_file(path, "app")
        assert found.name == "badge"
        assert found.signature == 'badge(text, tone="info")'

    def test_defaults_containing_commas_survive(self, project):
        path = write_component(
            project, "x", '{% macro f(a, opts=["one", "two"], b=1) %}x{% endmacro %}'
        )
        (found,) = parse_file(path, "app")
        assert found.args == 'a, opts=["one", "two"], b=1'

    def test_multi_line_signature_is_collapsed(self, project):
        path = write_component(
            project,
            "x",
            "{% macro f(\n    a,\n    b=2\n) %}x{% endmacro %}",
        )
        (found,) = parse_file(path, "app")
        assert found.signature == "f(a, b=2)"

    def test_whitespace_control_markers_are_handled(self, project):
        path = write_component(project, "x", "{%- macro f(a) -%}x{%- endmacro -%}")
        (found,) = parse_file(path, "app")
        assert found.name == "f"

    def test_several_macros_in_one_file(self, project):
        path = write_component(
            project,
            "form",
            "{% macro field(name) %}a{% endmacro %}\n{% macro area(name) %}b{% endmacro %}",
        )
        assert {c.name for c in parse_file(path, "app")} == {"field", "area"}

    def test_docblock_becomes_summary_and_usage(self, project):
        path = write_component(
            project,
            "x",
            "{#\nBadge Component\n===============\nA small status badge.\n\n"
            'Usage:\n    {{ badge("New") }}\n#}\n'
            "{% macro badge(text) %}b{% endmacro %}",
        )
        (found,) = parse_file(path, "app")
        assert found.summary == "A small status badge."
        assert '{{ badge("New") }}' in found.usage

    def test_file_without_docblock_still_parses(self, project):
        path = write_component(project, "x", "{% macro f(a) %}x{% endmacro %}")
        (found,) = parse_file(path, "app")
        assert found.summary == ""

    def test_import_line_matches_the_filename(self, project):
        path = write_component(project, "badge", "{% macro badge(t) %}b{% endmacro %}")
        (found,) = parse_file(path, "app")
        assert found.import_line == '{% from "components/badge.html" import badge %}'


class TestCollect:
    def test_framework_components_are_found(self):
        names = {c.name for c in collect()}
        # These ship with the framework; if one disappears the README and the
        # scaffolded CLAUDE.md are both wrong.
        assert {"button", "icon", "card", "modal", "toast", "spinner"} <= names

    def test_every_framework_file_is_represented(self):
        files = {
            p.stem for p in framework_components_dir().glob("*.html") if p.stem != "__init__"
        }
        assert {c.source.stem for c in collect()} == files

    def test_app_component_is_added(self, project):
        write_component(project, "badge", "{% macro badge(t) %}b{% endmacro %}")
        found = {c.name: c for c in collect(project)}
        assert found["badge"].origin == "app"

    def test_app_component_overrides_framework(self, project):
        write_component(project, "button", '{% macro button(text, mine=True) %}b{% endmacro %}')
        found = {c.name: c for c in collect(project) if c.source.stem == "button"}
        assert found["button"].origin == "app (overrides framework)"
        assert "mine=True" in found["button"].args

    def test_results_are_sorted(self, project):
        catalogue = collect(project)
        keys = [(c.source.stem, c.name) for c in catalogue]
        assert keys == sorted(keys)


class TestOutput:
    def test_plain_output_lists_signatures(self):
        result = CliRunner().invoke(components, [], catch_exceptions=False)
        assert result.exit_code == 0
        assert "button(text," in result.output
        assert "components/button.html" in result.output

    def test_json_output_is_machine_readable(self):
        result = CliRunner().invoke(components, ["--json"], catch_exceptions=False)
        payload = json.loads(result.output)
        button = next(c for c in payload if c["name"] == "button")
        assert button["file"] == "components/button.html"
        assert button["import"].startswith("{% from")
        assert button["origin"] == "framework"

    def test_markdown_output_has_a_section_per_file(self):
        text = to_markdown(collect())
        assert text.startswith("# Component Reference")
        assert "## `components/button.html`" in text
        assert "### `button(" in text

    def test_markdown_can_be_written_to_a_file(self, tmp_path):
        target = tmp_path / "components.md"
        result = CliRunner().invoke(
            components, ["--markdown", "-o", str(target)], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert target.read_text().startswith("# Component Reference")
        assert "Wrote" in result.output

    def test_app_override_is_flagged_in_output(self, project):
        write_component(project, "button", "{% macro button(t) %}b{% endmacro %}")
        result = CliRunner().invoke(
            components, ["--path", str(project)], catch_exceptions=False
        )
        assert "overrides framework" in result.output

    def test_non_project_directory_lists_framework_only(self, tmp_path):
        result = CliRunner().invoke(
            components, ["--path", str(tmp_path), "--json"], catch_exceptions=False
        )
        payload = json.loads(result.output)
        assert {c["origin"] for c in payload} == {"framework"}
