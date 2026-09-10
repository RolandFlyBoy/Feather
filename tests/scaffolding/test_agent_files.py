"""The AI-guidance files a scaffolded app gets.

An assistant working in a generated app needs three things: the rules, a way
to check its own work against them, and permission to run the commands that
do the checking without stopping to ask. These tests pin all three.
"""

import json

import pytest

from feather.cli._agent_files import SAFE_COMMANDS, agent_files

pytestmark = pytest.mark.scaffolding


class TestGeneratedContent:
    def test_claude_md_and_agents_md_are_identical(self):
        files = agent_files("MyApp", "# MyApp\n\nRules.")
        assert files["CLAUDE.md"] == files["AGENTS.md"]

    def test_both_carry_the_full_rules(self):
        files = agent_files("MyApp", "# MyApp\n\nNever use inline Tailwind.")
        for name in ("CLAUDE.md", "AGENTS.md"):
            assert "Never use inline Tailwind." in files[name]

    def test_guidance_points_at_the_checker(self):
        body = agent_files("MyApp", "rules")["AGENTS.md"]
        assert "feather check" in body
        assert "feather security-check" in body

    def test_guidance_points_at_the_component_catalogue(self):
        body = agent_files("MyApp", "rules")["AGENTS.md"]
        assert "feather components" in body

    def test_settings_are_valid_json(self):
        settings = json.loads(agent_files("MyApp", "rules")[".claude/settings.json"])
        assert settings["permissions"]["allow"] == SAFE_COMMANDS

    def test_allowed_commands_are_read_only(self):
        # A command that writes to a database or deploys must never be
        # pre-approved: the whole point is that the assistant can check its
        # work freely, not that it can change the world freely.
        forbidden = ("db upgrade", "db downgrade", "docker", "deploy", "rm ", "git push", "git commit")
        for command in SAFE_COMMANDS:
            assert not any(bad in command for bad in forbidden), command


class TestScaffoldedProject:
    def test_all_three_files_are_written(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        assert (project / "CLAUDE.md").exists()
        assert (project / "AGENTS.md").exists()
        assert (project / ".claude" / "settings.json").exists()

    def test_the_two_guidance_files_agree(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        assert (project / "CLAUDE.md").read_text() == (project / "AGENTS.md").read_text()

    def test_settings_parse(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        settings = json.loads((project / ".claude" / "settings.json").read_text())
        assert "feather check" in " ".join(settings["permissions"]["allow"])

    def test_auth_app_gets_them_too(self, scaffold_project):
        project = scaffold_project({"database": "postgresql", "include_auth": True})
        assert (project / "AGENTS.md").exists()
        assert "feather check" in (project / "AGENTS.md").read_text()
