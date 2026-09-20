"""The UI foundation a new app starts with.

What must not regress: the stylesheet, the macros and the behaviours are all
there and wired together, the tokens are editable Tailwind theme variables,
nothing in the foundation breaks the framework's own rules (no inline styles,
no native dialogs), and a page can show a file someone has just chosen or a
file kept in the app's bucket.
"""

from pathlib import Path

import pytest

from feather.core.security import csp_directives, storage_origin

SCAFFOLD = Path(__file__).resolve().parent.parent.parent / "feather" / "scaffold" / "base"
PACKAGE = Path(__file__).resolve().parent.parent.parent / "feather"


def test_a_new_app_gets_the_foundation_and_it_is_wired_in():
    css = (SCAFFOLD / "static" / "css" / "ui.css.tmpl").read_text()
    app_css = (SCAFFOLD / "static" / "css" / "app.css.tmpl").read_text()
    base = (SCAFFOLD / "templates" / "base.html.tmpl").read_text()

    assert "@theme" in css and "@apply" in css
    assert app_css.index('@import "tailwindcss";') < app_css.index('@import "./ui.css";')
    assert "/feather-static/ui.js" in base
    assert (PACKAGE / "static" / "ui.js").exists()
    assert (PACKAGE / "templates" / "components" / "ui.html").exists()


def test_the_tokens_are_editable_and_have_a_dark_mode():
    css = (SCAFFOLD / "static" / "css" / "ui.css.tmpl").read_text()
    for token in ("--color-bg", "--color-ink", "--color-accent", "--color-line", "--font-display", "--radius-ui"):
        assert token in css
    assert ".dark {" in css and css.index("@theme") < css.index(".dark {")


@pytest.mark.parametrize("piece", [
    ".ui-page", ".ui-nav", ".ui-btn", ".ui-input", ".ui-uploader", ".ui-card",
    ".ui-table", ".ui-gallery", ".ui-lightbox", ".ui-dialog", ".ui-notice",
    ".ui-empty", ".ui-skeleton",
])
def test_the_parts_an_app_needs_are_all_there(piece):
    assert piece in (SCAFFOLD / "static" / "css" / "ui.css.tmpl").read_text()


@pytest.mark.parametrize("macro", [
    "page_header", "empty_state", "uploader", "lightbox_item", "dialog", "notice", "skeleton",
])
def test_the_macros_are_all_there(macro):
    assert f"macro {macro}(" in (PACKAGE / "templates" / "components" / "ui.html").read_text()


def test_the_foundation_keeps_the_frameworks_own_rules():
    macros = (PACKAGE / "templates" / "components" / "ui.html").read_text()
    script = (PACKAGE / "static" / "ui.js").read_text()
    assert "<script" not in macros and 'style="' not in macros and "onclick" not in macros
    for native in ("alert(", "confirm(", "prompt("):
        assert native not in script.replace("showConfirm(", "").replace("showPrompt(", "")
    assert "addEventListener" in script


def test_the_agents_guide_describes_the_foundation():
    body = (SCAFFOLD / "_fragments" / "agents_body.md.tmpl").read_text()
    assert "The UI foundation" in body and "components/ui.html" in body and "data-uploader" in body


# ── Showing files ──────────────────────────────────────────────


def test_a_page_may_preview_a_file_before_it_is_uploaded():
    policy = csp_directives({})
    assert "blob:" in policy["img-src"] and "data:" in policy["img-src"]
    assert "blob:" in policy["media-src"]


def test_the_apps_own_bucket_is_allowed_to_serve_its_images():
    policy = csp_directives({"S3_ENDPOINT": "https://s3.example.com", "S3_BUCKET": "b"})
    assert "https://s3.example.com" in policy["img-src"]
    assert "https://s3.example.com" in policy["media-src"]
    # A public address wins, and a bare host still resolves to an origin.
    assert storage_origin({"S3_ENDPOINT": "https://s3.example.com", "S3_PUBLIC_URL": "https://cdn.example.com/files"}) == "https://cdn.example.com"
    assert storage_origin({"S3_ENDPOINT": "s3.example.com"}) == "https://s3.example.com"
    assert storage_origin({}) is None


def test_an_app_still_has_the_last_word():
    policy = csp_directives({"S3_ENDPOINT": "https://s3.example.com",
                             "FEATHER_CSP_DIRECTIVES": {"img-src": "'self'"}})
    assert policy["img-src"] == "'self'"
