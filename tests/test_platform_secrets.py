"""Secrets a hosting platform hands the app as files (Appentic's Key service
secrets) are in the environment before the app reads it."""

import os

from feather.core import config


def test_each_secret_file_becomes_a_variable_and_wins(tmp_path, monkeypatch):
    (tmp_path / "ANTHROPIC_API_KEY").write_text("sk-ant-secret")
    (tmp_path / "RESEND_API_KEY").write_text("re_secret")
    (tmp_path / "lower").write_text("ignored")
    (tmp_path / "TMP.tmp").write_text("ignored")
    monkeypatch.setenv("APPENTIC_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("RESEND_API_KEY", "re_from_the_environment")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config._load_platform_secrets()
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-secret"
    assert os.environ["RESEND_API_KEY"] == "re_secret", "a secret wins over a variable"
    assert "lower" not in os.environ and "TMP.tmp" not in os.environ


def test_no_folder_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("APPENTIC_SECRETS_DIR", str(tmp_path / "missing"))
    before = dict(os.environ)
    config._load_platform_secrets()
    assert dict(os.environ) == before


def test_a_link_out_of_the_folder_is_never_followed(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.write_text("not a secret")
    folder = tmp_path / "secrets"
    folder.mkdir()
    (folder / "LEAK").symlink_to(outside)
    monkeypatch.setenv("APPENTIC_SECRETS_DIR", str(folder))
    monkeypatch.delenv("LEAK", raising=False)
    config._load_platform_secrets()
    assert "LEAK" not in os.environ
