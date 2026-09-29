"""The avatar component (feather/templates/components/avatar.html): a picture
when there is one, otherwise an initial drawn on the page, never a request to
an avatar service elsewhere, which the content security policy blocks."""

from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[2] / "feather" / "templates"


def _render(user, **kwargs):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    macro = env.get_template("components/avatar.html").module.avatar
    return str(macro(user, **kwargs))


def test_someone_who_signed_in_by_email_gets_their_initial():
    html = _render(SimpleNamespace(email="roland.selmer@gmail.com", display_name=None, profile_image_url=None))
    assert ">R</span>" in html and "<img" not in html and "http" not in html


def test_a_display_name_wins_and_leading_symbols_are_skipped():
    assert ">M</span>" in _render(SimpleNamespace(email="x@y.z", display_name="  maya green", profile_image_url=""))
    assert ">4</span>" in _render(SimpleNamespace(email="_42@y.z", display_name=None, profile_image_url=None))


def test_a_google_picture_is_shown_when_there_is_one():
    html = _render(SimpleNamespace(email="a@b.c", display_name="A", profile_image_url="https://lh3.googleusercontent.com/p"),
                   size="xl")
    assert '<img src="https://lh3.googleusercontent.com/p"' in html and 'referrerpolicy="no-referrer"' in html
    assert "w-24 h-24" in html


def test_a_user_model_without_picture_or_name_fields_still_renders():
    assert ">A</span>" in _render(SimpleNamespace(email="ann@b.c"))
