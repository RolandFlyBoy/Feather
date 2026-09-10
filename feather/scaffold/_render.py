"""Apply the overlays for a set of options and substitute the tokens.

See this package's ``__init__`` for why substitution is ``str.replace`` of
``__FEATHER_NAME__`` tokens and nothing cleverer.
"""

import re
from pathlib import Path
from typing import Iterator

from ._manifest import OVERLAYS, TOKENS, overlays_for, token_values

#: Root of the overlay directories.
ROOT = Path(__file__).parent

#: Suffix every template file carries on top of its real extension.
TEMPLATE_SUFFIX = ".tmpl"

#: Directory inside an overlay holding the fragments that fill named slots.
FRAGMENT_DIR = "_fragments"

#: A path segment starting with this stands for one starting with a dot:
#: ``base/dot_env.tmpl`` is written as ``.env``. Dotfiles cannot live here
#: under their own names because setuptools' ``package-data`` globs skip
#: them, so a wheel would silently ship a project with no .env or .gitignore.
DOT_PREFIX = "dot_"

#: Matches one substitution token.
TOKEN_RE = re.compile(r"__FEATHER_[A-Z0-9_]+?__")

#: Substitution runs to a fixed point because fragments contain tokens of
#: their own. Two rounds is all any template needs today; the cap only stops a
#: token that expands to itself from hanging the generator.
MAX_PASSES = 10


def token(name: str) -> str:
    """Return the literal token text for a bare token name."""
    return f"__FEATHER_{name}__"


def overlay_dirs(options: dict) -> list[Path]:
    """Return the overlay directories that apply, in application order."""
    return [ROOT / name for name in overlays_for(options)]


def _walk(directory: Path) -> Iterator[Path]:
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            yield path


def project_path_for(relative: Path) -> str:
    """Return where a template file lands in the generated project."""
    parts = [
        "." + part[len(DOT_PREFIX) :] if part.startswith(DOT_PREFIX) else part
        for part in relative.parts
    ]
    path = "/".join(parts)
    if path.endswith(TEMPLATE_SUFFIX):
        path = path[: -len(TEMPLATE_SUFFIX)]
    return path


def collect(options: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(files, fragments)`` after applying every overlay in order.

    ``files`` maps a project-relative path to its unsubstituted body;
    ``fragments`` maps a bare token name to its unsubstituted body. A later
    overlay replaces what an earlier one supplied under the same key.
    """
    files: dict[str, str] = {}
    fragments: dict[str, str] = {}

    for directory in overlay_dirs(options):
        if not directory.is_dir():
            raise FileNotFoundError(f"scaffold overlay is missing: {directory}")
        frag_root = directory / FRAGMENT_DIR
        for path in _walk(directory):
            body = path.read_text()
            if frag_root in path.parents:
                fragments[path.name.split(".")[0].upper()] = body
            else:
                files[project_path_for(path.relative_to(directory))] = body
    return files, fragments


def vocabulary(options: dict) -> set[str]:
    """Every bare token name the renderer can supply for these options."""
    _, fragments = collect(options)
    return set(TOKENS) | set(fragments)


def all_fragment_names() -> set[str]:
    """Every fragment name any overlay defines, regardless of conditions."""
    names = set()
    for overlay in OVERLAYS:
        frag_root = ROOT / overlay.name / FRAGMENT_DIR
        if frag_root.is_dir():
            for path in frag_root.iterdir():
                if path.is_file():
                    names.add(path.name.split(".")[0].upper())
    return names


def substitute(body: str, values: dict[str, str]) -> str:
    """Replace every token in ``body``, repeating until nothing changes.

    A declared token with no value renders empty - that is how a slot for an
    overlay that is not applied disappears. An *undeclared* token raises: it
    is a typo in a template, and letting it through would ship the literal
    token into someone's new project.
    """
    for _ in range(MAX_PASSES):
        found = TOKEN_RE.findall(body)
        if not found:
            return body
        unknown = [t for t in found if t[len("__FEATHER_") : -2] not in values]
        if unknown:
            raise KeyError(
                "scaffold template uses undeclared token(s): " + ", ".join(sorted(set(unknown)))
            )
        for name, value in values.items():
            body = body.replace(token(name), value)
    raise RuntimeError("scaffold token substitution did not settle; a token expands to itself")


def _resolved_values(options: dict) -> dict[str, str]:
    """Every token's final value: option-derived first, then fragments."""
    _, fragments = collect(options)
    values = {name: "" for name in TOKENS}
    values.update(token_values(options))
    values.update({name: "" for name in all_fragment_names()})
    values.update(fragments)
    # Fragments contain tokens of their own, so resolve them before use.
    return {name: substitute(value, values) for name, value in values.items()}


def render_project(options: dict) -> dict[str, str]:
    """Return every scaffolded file for ``options`` as ``path -> content``."""
    files, _ = collect(options)
    values = _resolved_values(options)
    return {path: substitute(body, values) for path, body in sorted(files.items())}


def render_fragment(options: dict, name: str) -> str:
    """Return one fully substituted fragment.

    ``feather new`` needs the AGENTS.md body on its own: the body is written
    into two files by ``feather/cli/_agent_files.py`` rather than straight
    into the project, so it is a fragment rather than a project file.
    """
    return _resolved_values(options)[name.upper()]


def write_project(project_path: Path, options: dict) -> list[str]:
    """Render and write every scaffolded file under ``project_path``."""
    written = []
    for relative, content in render_project(options).items():
        target = Path(project_path) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(relative)
    return written
