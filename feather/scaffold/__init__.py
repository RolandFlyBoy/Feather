"""File bodies for the projects ``feather new`` scaffolds.

Everything ``feather new`` writes into a fresh project lives here as a real
file - ``app.css`` is CSS, ``base.html`` is HTML, ``user.py`` is Python -
instead of as a Python string literal inside ``feather/cli/new.py``. Editors
highlight them, ``git diff`` shows them as what they are, and the Jinja and
CSS braces they are full of need no escaping.

Layout
------
The files are grouped into *overlays*, each a directory that is copied over
the project in order when its condition holds::

    base/                 every app
    db/                   database is not "none"
    auth/                 authentication enabled
    auth_manual_approval/ auth and new users need admin approval
    auth_auto_approval/   auth and new users are approved on signup
    multi_tenant/         auth and tenant_mode == "multi"
    cache/ jobs/ cache_jobs/ storage/ email/ auth_email/

A later overlay replaces a file an earlier one wrote, so the multi-tenant
``models/user.py`` is a whole readable file rather than a chain of
``str.replace`` calls against the single-tenant one. ``_manifest.py`` maps the
options dict ``_create_project_files`` receives to the overlays that apply.

Substitution
------------
One mechanism, everywhere: ``str.replace`` of ``__FEATHER_NAME__`` tokens.

Not ``str.format`` and not Jinja. The generated files *are* Jinja templates
and Tailwind CSS, so ``{`` and ``}`` are everywhere and every ``format``-style
or Jinja-style placeholder would have to be escaped - which is exactly the
noise this package exists to remove. ``string.Template``'s ``$name`` is out
for the same reason: the generated JavaScript uses ``${...}`` template
literals. ``__UPPER_CASE__`` tokens appear nowhere in the generated output
(``tests/scaffolding/test_scaffold_overlays.py`` asserts it), and
``feather/cli/_docker_templates.py`` already substitutes with ``str.replace``
for the same reason, so this is the house style.

A token's value comes from one of two places:

* the options dict - ``__FEATHER_APP_NAME__``, ``__FEATHER_DB_URL__``;
* a *fragment*, a file under an overlay's ``_fragments/`` directory. The
  fragment ``jobs/_fragments/config_jobs.txt`` supplies
  ``__FEATHER_CONFIG_JOBS__``. Fragments are how the three files that are
  genuinely assembled from optional pieces - ``config.py``, ``.env`` and the
  AGENTS.md body - stay single readable skeletons with named slots. Like
  files, a later overlay's fragment replaces an earlier one's; a token with no
  fragment renders as the empty string.

Fragments may themselves contain tokens, so substitution runs to a fixed
point. Every token name a template may use is declared in ``_manifest.py``;
rendering raises on one that is not.

A path segment written ``dot_something`` lands as ``.something``
(``base/dot_env.tmpl`` is the project's ``.env``): setuptools' package-data
globs skip dotfiles, so a template named ``.env.tmpl`` builds fine from a
checkout and is missing from the wheel.

Template files carry a ``.tmpl`` suffix on top of their real extension
(``user.py.tmpl``, ``app.css.tmpl``). Without it setuptools would treat
``base/routes/`` as a Python subpackage because of the ``__init__.py``
template in it, pytest would collect ``base/tests/test_home.py``, and ruff
would try to lint files that are deliberately full of unsubstituted tokens.
"""

from ._render import render_fragment, render_project, write_project
from ._manifest import OVERLAYS, TOKENS, overlays_for, token_values

__all__ = [
    "render_fragment",
    "render_project",
    "write_project",
    "OVERLAYS",
    "TOKENS",
    "overlays_for",
    "token_values",
]
