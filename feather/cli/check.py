"""feather check - Verify a project against Feather's conventions.

The rules in a scaffolded app's CLAUDE.md are prose, so nothing enforces
them and an assistant editing the project has no way to tell whether its
change conforms. This command turns each one into a check that either passes
or points at a file and line::

    $ feather check
    templates/pages/home.html:14  inline-tailwind   class="px-4 py-2 bg-blue-600 text-white"
        Move it to static/css/app.css with @apply and use a class name.

    2 problems in 1 file (checked 34 files)

Exit code is 1 when any error-level finding is present, so it works as a
pre-commit hook and in CI. ``--json`` emits the same findings for tooling.

What it checks
--------------

Templates
    No inline ``<script>`` blocks, no inline event handlers (``onclick`` and
    friends), no inline Tailwind utility classes, no ``style=`` attributes.
    Google profile images carry ``referrerpolicy="no-referrer"``.

JavaScript
    No ``alert()``, ``confirm()`` or ``prompt()``: they cannot be styled,
    cannot be tested and block the event loop. No raw ``fetch()``: ApiUtility
    handles CSRF tokens, retries and error envelopes.

Routes
    Every route that is not explicitly public carries an auth decorator, and
    route handlers stay thin.

Models and services
    Queries against tenant-scoped models filter by tenant.

Imports
    Every module under models/, services/ and routes/ imports cleanly, which
    is the single fastest way to find a typo that would otherwise surface as
    a mysteriously missing route.
"""

import ast
import json as json_module
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

import click

ERROR = "error"
WARNING = "warning"

SEVERITY_COLORS = {ERROR: "red", WARNING: "yellow"}

#: Directories never worth walking.
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "migrations",
    "dist",
    "static/dist",
    ".feather-templates",
    ".pytest_cache",
}

#: Tailwind utility prefixes that indicate a class attribute is inline
#: styling rather than a semantic class name. Deliberately conservative:
#: these are the ones that carry visual weight and would otherwise need a
#: dark-mode variant alongside them.
TAILWIND_PREFIXES = (
    "bg-",
    "text-",
    "border-",
    "p-",
    "px-",
    "py-",
    "pt-",
    "pb-",
    "pl-",
    "pr-",
    "m-",
    "mx-",
    "my-",
    "mt-",
    "mb-",
    "ml-",
    "mr-",
    "w-",
    "h-",
    "flex",
    "grid",
    "gap-",
    "rounded",
    "shadow",
    "font-",
    "items-",
    "justify-",
    "space-x-",
    "space-y-",
    "hover:",
    "focus:",
    "dark:",
    "sm:",
    "md:",
    "lg:",
)

INLINE_HANDLER_RE = re.compile(
    r"\son(click|change|submit|input|load|error|focus|blur|keyup|keydown|"
    r"mouseover|mouseout|mouseenter|mouseleave)\s*=",
    re.IGNORECASE,
)
# An inline <script> is executable code in a template. A <script> carrying a
# src= is a normal asset include, and one with a data type (application/json,
# importmap, text/template) carries no executable code either - it is the
# supported way to hand server data to a module, and flagging it as an error
# made the rule fire on correct code.
SCRIPT_BLOCK_RE = re.compile(
    r"<script(?![^>]*\ssrc=)"
    r"(?![^>]*\stype\s*=\s*[\"']\s*(?:application/json|application/ld\+json|"
    r"importmap|speculationrules|text/template|text/x-template)\s*[\"'])"
    r"[^>]*>",
    re.IGNORECASE,
)
CLASS_ATTR_RE = re.compile(r'class\s*=\s*"([^"]*)"', re.IGNORECASE)
STYLE_ATTR_RE = re.compile(r'\sstyle\s*=\s*"([^"]*)"', re.IGNORECASE)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
GOOGLE_IMG_RE = re.compile(r"googleusercontent\.com", re.IGNORECASE)

NATIVE_DIALOG_RE = re.compile(r"(?<![\w.])(alert|confirm|prompt)\s*\(")
FETCH_RE = re.compile(r"(?<![\w.])fetch\s*\(")

#: Decorators that make a route's access explicit. A route carrying any of
#: these has had a decision made about it.
AUTH_DECORATORS = {
    "auth_required",
    "login_required",
    "admin_required",
    "role_required",
    "platform_admin_required",
    "tenant_required",
    "public",
    "login_only",
}

#: Route handlers longer than this probably belong in a service.
MAX_ROUTE_STATEMENTS = 15


class Finding:
    """One convention violation."""

    def __init__(
        self,
        path: Path,
        line: int,
        rule: str,
        message: str,
        remedy: str = "",
        severity: str = ERROR,
    ):
        self.path = path
        self.line = line
        self.rule = rule
        self.message = message
        self.remedy = remedy
        self.severity = severity

    def as_dict(self, root: Path) -> dict:
        try:
            relative = str(self.path.relative_to(root))
        except ValueError:
            relative = str(self.path)
        return {
            "file": relative,
            "line": self.line,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "remedy": self.remedy,
        }


# =============================================================================
# Walking the project
# =============================================================================


def _should_skip(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in SKIP_DIRS for part in parts)


def iter_files(root: Path, *patterns: str) -> Iterable[Path]:
    """Yield project files matching any glob, skipping vendor directories."""
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and not _should_skip(path, root):
                yield path


def line_of(text: str, index: int) -> int:
    """1-based line number of a character offset."""
    return text.count("\n", 0, index) + 1


# =============================================================================
# Template checks
# =============================================================================


def check_templates(root: Path) -> list:
    findings = []
    for path in iter_files(root, "templates/**/*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")

        for match in SCRIPT_BLOCK_RE.finditer(text):
            findings.append(
                Finding(
                    path,
                    line_of(text, match.start()),
                    "inline-script",
                    "inline <script> block",
                    "Move the code to static/js/ (shared) or static/islands/ "
                    "(component) and load it with a src attribute.",
                )
            )

        for match in INLINE_HANDLER_RE.finditer(text):
            findings.append(
                Finding(
                    path,
                    line_of(text, match.start()),
                    "inline-handler",
                    f"inline event handler{match.group(0).rstrip('=').rstrip()}",
                    "Use an hx-* attribute for server interactions, or a "
                    "data-action attribute handled by an island.",
                )
            )

        for match in STYLE_ATTR_RE.finditer(text):
            findings.append(
                Finding(
                    path,
                    line_of(text, match.start()),
                    "inline-style",
                    "inline style attribute",
                    "Move it to static/css/app.css.",
                )
            )

        for match in CLASS_ATTR_RE.finditer(text):
            classes = match.group(1).split()
            utilities = [c for c in classes if c.startswith(TAILWIND_PREFIXES)]
            if utilities:
                shown = " ".join(utilities[:4])
                if len(utilities) > 4:
                    shown += f" (+{len(utilities) - 4} more)"
                findings.append(
                    Finding(
                        path,
                        line_of(text, match.start()),
                        "inline-tailwind",
                        f'class="{shown}"',
                        "Move it to static/css/app.css with @apply and use a "
                        "semantic class name, so dark-mode variants live in "
                        "one place.",
                        severity=WARNING,
                    )
                )

        for match in IMG_TAG_RE.finditer(text):
            tag = match.group(0)
            if GOOGLE_IMG_RE.search(tag) and "referrerpolicy" not in tag.lower():
                findings.append(
                    Finding(
                        path,
                        line_of(text, match.start()),
                        "google-image-referrer",
                        "Google profile image without referrerpolicy",
                        'Add referrerpolicy="no-referrer", or Google returns '
                        "429 and the avatar silently breaks.",
                    )
                )
    return findings


# =============================================================================
# JavaScript checks
# =============================================================================


def _strip_js_comments_and_strings(text: str) -> str:
    """Blank out comments and string literals, preserving offsets.

    Keeps character positions intact so line numbers stay correct, while
    stopping a word inside a comment or a message string from being reported
    as a call.
    """
    out = list(text)
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < length else ""
        if ch == "/" and nxt == "/":
            while i < length and text[i] != "\n":
                out[i] = " "
                i += 1
        elif ch == "/" and nxt == "*":
            while i < length and not (text[i] == "*" and i + 1 < length and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            for j in range(i, min(i + 2, length)):
                out[j] = " "
            i += 2
        elif ch in "\"'`":
            quote = ch
            out[i] = " "
            i += 1
            while i < length and text[i] != quote:
                if text[i] == "\\":
                    out[i] = " "
                    i += 1
                if i < length:
                    if text[i] != "\n":
                        out[i] = " "
                    i += 1
            if i < length:
                out[i] = " "
                i += 1
        else:
            i += 1
    return "".join(out)


def check_javascript(root: Path) -> list:
    findings = []
    for path in iter_files(root, "static/js/**/*.js", "static/islands/**/*.js"):
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = _strip_js_comments_and_strings(raw)

        for match in NATIVE_DIALOG_RE.finditer(text):
            name = match.group(1)
            findings.append(
                Finding(
                    path,
                    line_of(raw, match.start()),
                    "native-dialog",
                    f"{name}() blocks the page and cannot be styled or tested",
                    {
                        "alert": "Use showToast() or a modal component.",
                        "confirm": "Use hx-confirm, which routes through the "
                        "app's confirm modal.",
                        "prompt": "Use window.showPrompt().",
                    }[name],
                )
            )

        for match in FETCH_RE.finditer(text):
            findings.append(
                Finding(
                    path,
                    line_of(raw, match.start()),
                    "raw-fetch",
                    "raw fetch() call",
                    "Use ApiUtility from /feather-static/api.js: it attaches "
                    "the CSRF token, retries, and unwraps the error envelope.",
                )
            )
    return findings


# =============================================================================
# Python checks
# =============================================================================


def _decorator_names(node: ast.AST) -> set:
    names = set()
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _is_route(names: set) -> bool:
    return bool(names & {"route", "get", "post", "put", "patch", "delete"})


def check_routes(root: Path) -> list:
    findings = []
    for path in iter_files(root, "routes/**/*.py"):
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            findings.append(
                Finding(path, exc.lineno or 1, "syntax-error", f"cannot parse: {exc.msg}")
            )
            continue

        # A module-level `public = True` or a `# feather: public` comment
        # marks a whole file as deliberately unauthenticated.
        module_public = "feather: public" in source

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names = _decorator_names(node)
            if not _is_route(names):
                continue

            if not module_public and not (names & AUTH_DECORATORS):
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "unprotected-route",
                        f"route {node.name}() has no auth decorator",
                        "Add @auth_required (or @admin_required). If the route "
                        "is deliberately public, mark it with a "
                        "'# feather: public' comment in the module.",
                        severity=WARNING,
                    )
                )

            statements = sum(1 for _ in ast.walk(node) if isinstance(_, ast.stmt))
            if statements > MAX_ROUTE_STATEMENTS:
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "fat-route",
                        f"route {node.name}() has {statements} statements",
                        "Routes validate input, call a service and return. "
                        "Move the logic into a service.",
                        severity=WARNING,
                    )
                )
    return findings


def _tenant_scoped_models(root: Path) -> set:
    """Names of model classes that use TenantScopedMixin."""
    scoped = set()
    for path in iter_files(root, "models/**/*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                if "TenantScopedMixin" in bases:
                    scoped.add(node.name)
    return scoped


def check_tenant_isolation(root: Path) -> list:
    """Flag queries on tenant-scoped models that never mention a tenant."""
    scoped = _tenant_scoped_models(root)
    if not scoped:
        return []

    findings = []
    for path in iter_files(root, "services/**/*.py", "routes/**/*.py"):
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segment = ast.get_source_segment(source, node) or ""
            if "tenant" in segment.lower():
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Attribute)
                    and inner.attr == "query"
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id in scoped
                ):
                    findings.append(
                        Finding(
                            path,
                            inner.lineno,
                            "tenant-isolation",
                            f"{inner.value.id}.query with no tenant filter in {node.name}()",
                            f"Use {inner.value.id}.for_tenant(get_current_tenant_id()) "
                            "so one tenant cannot read another's rows.",
                        )
                    )
                    break
    return findings


def check_imports(root: Path) -> list:
    """Compile every discoverable module, so a typo fails loudly here.

    Feather imports these at startup, and before 0.9.6 an ImportError was
    swallowed, which made a route silently disappear. Compiling catches the
    syntax half of that without the side effects of a real import.
    """
    findings = []
    for path in iter_files(root, "models/**/*.py", "services/**/*.py", "routes/**/*.py"):
        if path.name == "__init__.py":
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            findings.append(
                Finding(
                    path,
                    exc.lineno or 1,
                    "syntax-error",
                    f"{exc.msg}",
                    "Feather's discovery imports this module at startup; a "
                    "syntax error here removes its routes or models.",
                )
            )
    return findings


# =============================================================================
# Orphan islands
# =============================================================================


def check_islands(root: Path) -> list:
    """Islands that no template mounts, and mounts with no island."""
    island_dir = root / "static" / "islands"

    defined = {p.stem for p in iter_files(root, "static/islands/*.js")}

    mounted = set()
    for path in iter_files(root, "templates/**/*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        mounted.update(re.findall(r'data-island\s*=\s*"([^"]+)"', text))

    findings = []
    for name in sorted(defined - mounted):
        findings.append(
            Finding(
                island_dir / f"{name}.js",
                1,
                "orphan-island",
                f"island '{name}' is never mounted",
                f'No template has data-island="{name}". Delete the file or '
                "mount it.",
                severity=WARNING,
            )
        )
    for name in sorted(mounted - defined):
        findings.append(
            Finding(
                root / "templates",
                1,
                "missing-island",
                f"template mounts island '{name}' but static/islands/{name}.js does not exist",
                "Create the island or remove the data-island attribute.",
            )
        )
    return findings


# =============================================================================
# Runner
# =============================================================================

CHECKS = {
    "templates": check_templates,
    "javascript": check_javascript,
    "routes": check_routes,
    "tenancy": check_tenant_isolation,
    "imports": check_imports,
    "islands": check_islands,
}


def run_checks(root: Path, only: Optional[str] = None) -> list:
    findings = []
    for name, fn in CHECKS.items():
        if only and name != only:
            continue
        findings.extend(fn(root))
    findings.sort(key=lambda f: (str(f.path), f.line))
    return findings


def is_project(root: Path) -> bool:
    return (root / "app.py").exists()


@click.command(name="check")
@click.option("--json", "as_json", is_flag=True, help="Emit findings as JSON.")
@click.option(
    "--only",
    type=click.Choice(sorted(CHECKS)),
    default=None,
    help="Run a single group of checks.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors (exit 1 when any finding is reported).",
)
@click.option(
    "--per-rule",
    default=10,
    show_default=True,
    help="Findings to print per rule before summarising. 0 prints everything.",
)
@click.option("--path", "project_path", default=".", help="Project directory (default: current).")
def check(as_json: bool, only: Optional[str], strict: bool, per_rule: int, project_path: str):
    """Check the project against Feather's conventions.

    Enforces the rules a scaffolded app's CLAUDE.md states in prose: no
    inline styles, scripts or event handlers in templates, no native browser
    dialogs, no raw fetch(), routes that declare their access, and tenant
    filtering on tenant-scoped models.

    Exits 1 when an error-level finding is present, so it works as a
    pre-commit hook or a CI step.

    \b
    Examples:
      feather check                  Check the current project
      feather check --only templates Only the template rules
      feather check --strict         Warnings fail too
      feather check --json           Machine-readable output
    """
    root = Path(project_path).resolve()
    if not root.exists():
        raise click.ClickException(f"Directory not found: {project_path}")
    if not is_project(root):
        raise click.ClickException(
            f"Not a Feather project: no app.py in {root}. "
            "Run this from your project root, or pass --path."
        )

    findings = run_checks(root, only)
    if per_rule <= 0:
        per_rule = len(findings) or 1
    errors = [f for f in findings if f.severity == ERROR]
    warnings = [f for f in findings if f.severity == WARNING]

    if as_json:
        click.echo(
            json_module.dumps(
                {
                    "ok": not errors and not (strict and warnings),
                    "counts": {"error": len(errors), "warning": len(warnings)},
                    "findings": [f.as_dict(root) for f in findings],
                },
                indent=2,
            )
        )
    else:
        shown_per_rule = {}
        for finding in findings:
            seen = shown_per_rule.get(finding.rule, 0)
            if seen >= per_rule:
                shown_per_rule[finding.rule] = seen + 1
                continue
            shown_per_rule[finding.rule] = seen + 1
            location = f"{finding.as_dict(root)['file']}:{finding.line}"
            colour = SEVERITY_COLORS[finding.severity]
            click.echo(
                f"{click.style(location, fg='cyan')}  "
                f"{click.style(finding.rule, fg=colour, bold=True)}  "
                f"{finding.message}"
            )
            if finding.remedy:
                click.echo(f"    {finding.remedy}")

        for rule, count in sorted(shown_per_rule.items()):
            if count > per_rule:
                click.echo(
                    click.style(
                        f"    ... and {count - per_rule} more {rule} "
                        f"(use --per-rule 0 to see them all)",
                        fg="bright_black",
                    )
                )

        if findings:
            click.echo()
            click.echo(
                f"{len(errors)} error{'s' if len(errors) != 1 else ''}, "
                f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''} "
                f"in {len({f.path for f in findings})} file(s)"
            )
        else:
            click.echo(click.style("No problems found.", fg="green"))

    if errors or (strict and warnings):
        sys.exit(1)
