"""Tests for the scaffold overlay mechanism itself.

``feather/scaffold`` holds the bodies of every file ``feather new`` writes, as
real files grouped into overlays. These tests are about the mechanism - that
the overlays are all present, that every token a template uses is one the
renderer supplies, and that nothing renders with a token still in it. What the
files *say* is covered by the rest of ``tests/scaffolding``.
"""

import re
from pathlib import Path

import pytest

from feather.scaffold import OVERLAYS, TOKENS, overlays_for, render_project
from feather.scaffold._render import (
    DOT_PREFIX,
    FRAGMENT_DIR,
    ROOT,
    TEMPLATE_SUFFIX,
    TOKEN_RE,
    all_fragment_names,
    collect,
    project_path_for,
)

pytestmark = pytest.mark.scaffolding


#: One options dict per shape of app the CLI can produce. Every overlay is
#: applied by at least one of them, and every pair that can combine does.
OPTION_SETS = {
    "simple": dict(name="simple_app", database="none"),
    "sqlite_no_auth": dict(name="sqlite_app", database="sqlite", db_url="sqlite:///instance/app.db"),
    "single_tenant": dict(
        name="single_app",
        database="postgresql",
        db_url="postgresql://localhost/single_app",
        include_auth=True,
        tenant_mode="single",
        admin_email="admin@example.com",
    ),
    "single_tenant_auto_approve": dict(
        name="auto_app",
        database="postgresql",
        db_url="postgresql://localhost/auto_app",
        include_auth=True,
        tenant_mode="single",
        auto_approve_users=True,
        admin_email="admin@example.com",
    ),
    "multi_tenant": dict(
        name="multi_app",
        database="postgresql",
        db_url="postgresql://localhost/multi_app",
        include_auth=True,
        tenant_mode="multi",
        admin_email="admin@example.com",
    ),
    "everything": dict(
        name="full_app",
        database="postgresql",
        db_url="postgresql://localhost/full_app",
        include_auth=True,
        tenant_mode="multi",
        auto_approve_users=True,
        include_cache=True,
        include_jobs=True,
        include_storage=True,
        storage_backend="gcs",
        include_email=True,
        admin_email="admin@example.com",
        user_fields={"display_name": True, "profile_image_url": True},
    ),
    "features_without_auth": dict(
        name="worker_app",
        database="none",
        include_cache=True,
        include_jobs=True,
        include_storage=True,
        storage_backend="gcs",
    ),
}


def _template_files():
    """Every template file in the package, as (overlay, path) pairs."""
    for overlay in OVERLAYS:
        directory = ROOT / overlay.name
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                yield overlay.name, path


class TestManifest:
    """The manifest and the directories on disk agree."""

    def test_every_overlay_directory_exists(self):
        for overlay in OVERLAYS:
            assert (ROOT / overlay.name).is_dir(), f"missing overlay directory: {overlay.name}"

    def test_no_orphan_directories(self):
        """Nothing sits in the package that no overlay would ever copy."""
        known = {o.name for o in OVERLAYS}
        strays = [
            p.name
            for p in ROOT.iterdir()
            if p.is_dir() and not p.name.startswith("__") and p.name not in known
        ]
        assert strays == [], f"directories no overlay applies: {strays}"

    def test_base_applies_to_every_app(self):
        for options in OPTION_SETS.values():
            assert overlays_for(options)[0] == "base"

    def test_conditional_overlays_are_conditional(self):
        """Each non-base overlay is skipped by at least one option set."""
        applied = [set(overlays_for(o)) for o in OPTION_SETS.values()]
        for overlay in OVERLAYS[1:]:
            assert any(
                overlay.name not in names for names in applied
            ), f"{overlay.name} is applied unconditionally"

    def test_every_overlay_is_reachable(self):
        """Each overlay is applied by at least one option set."""
        applied = set()
        for options in OPTION_SETS.values():
            applied.update(overlays_for(options))
        unreachable = {o.name for o in OVERLAYS} - applied
        assert unreachable == set(), f"overlays no option set reaches: {unreachable}"

    def test_overlay_order_is_stable(self):
        """A more specific overlay always comes after the one it refines."""
        order = [o.name for o in OVERLAYS]
        for earlier, later in [
            ("base", "db"),
            ("db", "auth"),
            ("auth", "auth_manual_approval"),
            ("auth", "auth_auto_approval"),
            ("auth", "multi_tenant"),
            ("cache", "cache_jobs"),
            ("jobs", "cache_jobs"),
            ("auth", "auth_email"),
            ("email", "auth_email"),
        ]:
            assert order.index(earlier) < order.index(later), f"{later} must follow {earlier}"


class TestTemplateFiles:
    """Every file in the package is a well-formed template."""

    def test_all_templates_carry_the_suffix(self):
        """A stray ``.py`` under an overlay would be imported or linted."""
        bad = [
            str(p.relative_to(ROOT))
            for _, p in _template_files()
            if not p.name.endswith(TEMPLATE_SUFFIX)
        ]
        assert bad == [], f"template files without a {TEMPLATE_SUFFIX} suffix: {bad}"

    def test_templates_keep_a_real_extension(self):
        """``user.py.tmpl``, not ``user.tmpl`` - so editors still highlight it.

        A ``dot_`` name is exempt: ``.gitignore`` has no extension to keep.
        """
        bad = []
        for _, path in _template_files():
            stem = path.name[: -len(TEMPLATE_SUFFIX)]
            if not stem.startswith(DOT_PREFIX) and "." not in stem:
                bad.append(str(path.relative_to(ROOT)))
        assert bad == [], f"templates with no real extension: {bad}"

    def test_no_template_is_itself_a_dotfile(self):
        """setuptools' package-data globs skip dotfiles.

        A template named ``.env.tmpl`` renders fine from a checkout and is
        silently absent from the wheel, so a pip-installed ``feather new``
        would write a project with no ``.env``. Dotfiles are spelled
        ``dot_env.tmpl`` instead.
        """
        dotfiles = [
            str(p.relative_to(ROOT))
            for _, p in _template_files()
            if any(part.startswith(".") for part in p.relative_to(ROOT).parts)
        ]
        assert dotfiles == [], f"dotfile templates will not ship in the wheel: {dotfiles}"

    def test_dot_prefix_maps_to_a_dotfile(self):
        assert project_path_for(Path("dot_env.tmpl")) == ".env"
        assert project_path_for(Path("static/css/app.css.tmpl")) == "static/css/app.css"

    @pytest.mark.parametrize("label", sorted(OPTION_SETS))
    def test_dotfiles_reach_the_project(self, label):
        files = render_project(OPTION_SETS[label])
        assert ".env" in files
        assert ".gitignore" in files

    def test_no_absolute_filesystem_paths(self):
        """An absolute path here would be baked into someone else's project.

        The scaffolded ``app.css`` learned this the hard way: pointing Tailwind
        at the installed package's absolute path silently dropped every
        framework component class as soon as the project was built anywhere
        but the machine that scaffolded it.
        """
        absolute = re.compile(r"(?:^|[\s\"'(=])(/Users/|/home/|/private/|/tmp/|[A-Z]:\\\\)")
        offenders = []
        for _, path in _template_files():
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                if absolute.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
        assert offenders == [], "absolute paths in templates:\n" + "\n".join(offenders)

    def test_no_template_is_empty_by_accident(self):
        """Only ``tests/__init__.py`` is legitimately empty."""
        empty = [
            str(p.relative_to(ROOT))
            for _, p in _template_files()
            if p.read_text() == "" and p.name != "__init__.py" + TEMPLATE_SUFFIX
        ]
        assert empty == [], f"unexpectedly empty templates: {empty}"


class TestTokens:
    """Every token used is declared, and every token declared is used."""

    def test_every_token_used_is_supplied(self):
        """A typo'd token would otherwise ship as literal text."""
        declared = set(TOKENS) | all_fragment_names()
        undeclared = {}
        for _, path in _template_files():
            for found in TOKEN_RE.findall(path.read_text()):
                name = found[len("__FEATHER_") : -2]
                if name not in declared:
                    undeclared.setdefault(name, []).append(str(path.relative_to(ROOT)))
        assert undeclared == {}, f"tokens no overlay or option supplies: {undeclared}"

    def test_every_declared_token_is_used(self):
        """A token nothing references is dead weight in the manifest."""
        used = set()
        for _, path in _template_files():
            for found in TOKEN_RE.findall(path.read_text()):
                used.add(found[len("__FEATHER_") : -2])
        # The AGENTS.md body is a fragment that no template includes: `feather
        # new` asks for it by name and hands it to _agent_files, which writes
        # it into both AGENTS.md and CLAUDE.md.
        used.add("AGENTS_BODY")
        unused = (set(TOKENS) | all_fragment_names()) - used
        assert unused == set(), f"declared but never referenced: {unused}"

    def test_fragments_are_not_written_as_project_files(self):
        """``_fragments`` fills slots; it is not part of the project tree."""
        for name, options in OPTION_SETS.items():
            files = render_project(options)
            assert not any(FRAGMENT_DIR in path for path in files), name

    def test_unknown_token_raises(self):
        """A template with a bad token fails loudly rather than silently."""
        from feather.scaffold._render import substitute

        with pytest.raises(KeyError):
            substitute("hello __FEATHER_NO_SUCH_TOKEN__", {"APP_NAME": "x"})


class TestRendering:
    """Rendering each option set produces a complete project."""

    @pytest.mark.parametrize("label", sorted(OPTION_SETS))
    def test_no_token_survives_rendering(self, label):
        for path, body in render_project(OPTION_SETS[label]).items():
            assert not TOKEN_RE.search(body), f"{label}: unsubstituted token in {path}"

    @pytest.mark.parametrize("label", sorted(OPTION_SETS))
    def test_no_placeholder_words_survive(self, label):
        """The pre-overlay generator left ``..._PLACEHOLDER`` markers behind."""
        for path, body in render_project(OPTION_SETS[label]).items():
            assert "PLACEHOLDER" not in body, f"{label}: placeholder marker left in {path}"

    @pytest.mark.parametrize("label", sorted(OPTION_SETS))
    def test_python_files_compile(self, label):
        for path, body in render_project(OPTION_SETS[label]).items():
            if path.endswith(".py"):
                compile(body, path, "exec")

    @pytest.mark.parametrize("label", sorted(OPTION_SETS))
    def test_app_name_reaches_the_project(self, label):
        options = OPTION_SETS[label]
        assert options["name"] in render_project(options)[".env"]

    def test_a_later_overlay_replaces_an_earlier_file(self):
        """The overlay order is what makes the multi-tenant variants win."""
        single = render_project(OPTION_SETS["single_tenant"])
        multi = render_project(OPTION_SETS["multi_tenant"])
        assert single["models/user.py"] != multi["models/user.py"]
        assert "tenant_id" in multi["models/user.py"]
        assert "tenant_id" not in single["models/user.py"]

    def test_a_later_overlay_adds_files(self):
        single = render_project(OPTION_SETS["single_tenant"])
        multi = render_project(OPTION_SETS["multi_tenant"])
        assert "models/tenant.py" in multi
        assert "models/tenant.py" not in single

    def test_collect_is_deterministic(self):
        for options in OPTION_SETS.values():
            assert collect(options) == collect(options)

    def test_rendering_is_deterministic(self):
        for options in OPTION_SETS.values():
            assert render_project(options) == render_project(options)


class TestOverlayContentInvariants:
    """The overlay split must not lose what the string surgery used to add.

    The multi-tenant admin service used to be built by rewriting the
    single-tenant one with a chain of ``str.replace`` calls. A drifting base
    string would have made those silently no-op and shipped an admin panel
    that reads every tenant's users. Two whole files cannot drift that way,
    but they can be edited apart, so assert the scoping directly.
    """

    TENANT_SCOPED = [
        "get_all_users",
        "search_users",
        "get_user_detail",
        "toggle_user_status",
        "update_user_role",
        "get_user_stats",
        "get_user_growth",
        "find_user_by_email",
    ]

    def test_multi_tenant_admin_service_scopes_every_user_query(self):
        body = render_project(OPTION_SETS["multi_tenant"])["services/admin_service.py"]
        for name in self.TENANT_SCOPED:
            start = body.index(f"def {name}(")
            end = body.find("\n    def ", start)
            method = body[start : end if end != -1 else len(body)]
            assert "_get_tenant_id()" in method, f"{name} is not tenant-scoped"

    def test_single_tenant_admin_service_has_no_tenant_scoping(self):
        body = render_project(OPTION_SETS["single_tenant"])["services/admin_service.py"]
        assert "_get_tenant_id" not in body

    def test_pending_page_only_exists_when_approval_is_manual(self):
        manual = render_project(OPTION_SETS["single_tenant"])
        auto = render_project(OPTION_SETS["single_tenant_auto_approve"])
        assert "templates/pages/account/pending.html" in manual
        assert "templates/pages/account/pending.html" not in auto
        assert "account_pending" in manual["routes/pages/account.py"]
        assert "account_pending" not in auto["routes/pages/account.py"]

    def test_email_routes_only_exist_with_email_and_auth(self):
        assert "send_email" not in render_project(OPTION_SETS["multi_tenant"])[
            "routes/pages/admin.py"
        ]
        assert "send_email" in render_project(OPTION_SETS["everything"])["routes/pages/admin.py"]

    def test_the_sidebar_logo_is_stored_once(self):
        """It used to be pasted four times across the admin layouts."""
        marker = '<svg class="sidebar-logo-icon"'
        sources = [p for _, p in _template_files() if marker in p.read_text()]
        assert len(sources) == 1, f"logo duplicated across {[str(p) for p in sources]}"
        rendered = render_project(OPTION_SETS["multi_tenant"])["templates/pages/admin/base.html"]
        assert rendered.count(marker) == 2  # mobile drawer and desktop sidebar
