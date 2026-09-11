"""`feather: allow <rule>` turns off one rule on one line.

A rule with no way to say "not here" is a rule people turn off altogether,
and a blanket disable loses the other ninety per cent of the value. The
motivating case is a progress bar whose width comes from per-row data: it
cannot move to a stylesheet, and setting it from JavaScript trades the lint
error for a flash of empty bar on every render.
"""

import pytest

from feather.cli.check import ALLOW_RE, run_checks, suppressed_rules


class TestMarkerParsing:
    @pytest.mark.parametrize(
        "line,expected",
        [
            ("{# feather: allow inline-style #}", {"inline-style"}),
            ("<!-- feather: allow inline-script -->", {"inline-script"}),
            ("// feather: allow raw-fetch", {"raw-fetch"}),
            ("/* feather: allow inline-style */", {"inline-style"}),
            ("# feather: allow native-dialog", {"native-dialog"}),
            ("{# feather: allow inline-style, inline-script #}", {"inline-style", "inline-script"}),
            ("{# FEATHER: ALLOW Inline-Style #}", {"inline-style"}),
        ],
    )
    def test_parses(self, line, expected):
        assert suppressed_rules([line, "<div>"], 2) == expected

    def test_reason_after_a_dash_is_not_part_of_the_rule(self):
        line = "{# feather: allow inline-style - width is per-row data #}"
        assert suppressed_rules([line, "<div>"], 2) == {"inline-style"}

    def test_reason_after_an_em_dash(self):
        line = "{# feather: allow inline-style — width is per-row data #}"
        assert suppressed_rules([line, "<div>"], 2) == {"inline-style"}

    def test_unrelated_comment_suppresses_nothing(self):
        assert suppressed_rules(["{# just a note #}", "<div>"], 2) == set()

    def test_the_words_alone_are_not_a_marker(self):
        assert suppressed_rules(["allow inline style", "<div>"], 2) == set()


class TestPlacement:
    def test_same_line(self):
        lines = ['<div style="width:1%"> {# feather: allow inline-style #}']
        assert "inline-style" in suppressed_rules(lines, 1)

    def test_line_above(self):
        lines = ["{# feather: allow inline-style #}", '<div style="width:1%">']
        assert "inline-style" in suppressed_rules(lines, 2)

    def test_two_lines_above_is_too_far(self):
        lines = ["{# feather: allow inline-style #}", "", '<div style="width:1%">']
        assert suppressed_rules(lines, 3) == set()

    def test_out_of_range_is_not_an_error(self):
        assert suppressed_rules([], 5) == set()
        assert suppressed_rules(["x"], 99) == set()


class TestEndToEnd:
    """Through run_checks, against a real project tree."""

    @staticmethod
    def _project(tmp_path):
        (tmp_path / "app.py").write_text("from feather import Feather\napp = Feather(__name__)\n")
        (tmp_path / "templates").mkdir()
        return tmp_path

    def test_unsuppressed_style_is_reported(self, tmp_path):
        project = self._project(tmp_path)
        (project / "templates" / "p.html").write_text('<div style="width:50%"></div>\n')
        rules = {f.rule for f in run_checks(project)}
        assert "inline-style" in rules

    def test_suppressed_style_is_not_reported(self, tmp_path):
        project = self._project(tmp_path)
        (project / "templates" / "p.html").write_text(
            "{# feather: allow inline-style - width is per-row data #}\n"
            '<div style="width:50%"></div>\n'
        )
        rules = {f.rule for f in run_checks(project)}
        assert "inline-style" not in rules

    def test_suppressing_one_rule_leaves_the_others(self, tmp_path):
        project = self._project(tmp_path)
        (project / "templates" / "p.html").write_text(
            "{# feather: allow inline-style #}\n"
            '<div style="width:50%" onclick="go()"></div>\n'
        )
        rules = {f.rule for f in run_checks(project)}
        assert "inline-style" not in rules
        assert "inline-handler" in rules

    def test_a_marker_does_not_suppress_the_next_line(self, tmp_path):
        project = self._project(tmp_path)
        (project / "templates" / "p.html").write_text(
            "{# feather: allow inline-style #}\n"
            '<div style="width:50%"></div>\n'
            '<div style="width:60%"></div>\n'
        )
        styles = [f for f in run_checks(project) if f.rule == "inline-style"]
        assert len(styles) == 1
        assert styles[0].line == 3
