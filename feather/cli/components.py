"""feather components - List the component macros available to templates.

The framework ships Jinja2 macros under ``feather/templates/components/``,
and an app can override any of them or add its own under
``templates/components/``. Nothing listed them, so the only way to learn a
macro's arguments was to open the file -- and the README's list had drifted
out of date. This command reads the macros themselves, so it cannot::

    $ feather components
    button(text, type="button", variant="primary", icon=None, class="")
        Styled button with variants and icon support.
        {% from "components/button.html" import button %}

``--json`` emits the same catalogue for tooling, and ``--markdown`` writes
the reference an AI assistant can read alongside the app's CLAUDE.md.
"""

import json as json_module
import re
from pathlib import Path
from typing import Optional

import click

#: `{% macro name(args) %}` with the argument list captured whole, so
#: defaults containing commas or parentheses survive.
MACRO_RE = re.compile(r"{%-?\s*macro\s+(\w+)\s*\((.*?)\)\s*-?%}", re.DOTALL)

#: The leading `{# ... #}` comment a component file opens with.
DOCBLOCK_RE = re.compile(r"{#(.*?)#}", re.DOTALL)


class Component:
    """One macro, with the text that documents it."""

    def __init__(self, name: str, args: str, source: Path, summary: str, usage: list, origin: str):
        self.name = name
        self.args = args
        self.source = source
        self.summary = summary
        self.usage = usage
        self.origin = origin

    @property
    def signature(self) -> str:
        return f"{self.name}({self.args})"

    @property
    def import_line(self) -> str:
        return f'{{% from "components/{self.source.stem}.html" import {self.name} %}}'

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "signature": self.signature,
            "arguments": self.args,
            "file": f"components/{self.source.stem}.html",
            "summary": self.summary,
            "usage": self.usage,
            "origin": self.origin,
            "import": self.import_line,
        }


def _normalise_args(args: str) -> str:
    """Collapse a macro's argument list onto one line."""
    return " ".join(args.split())


def _parse_docblock(text: str) -> tuple:
    """Return (summary, usage lines) from a component's opening comment.

    The convention in these files is a title, an underline, a sentence or
    two of description, then a "Usage:" block of example calls.
    """
    match = DOCBLOCK_RE.search(text)
    if not match:
        return "", []

    lines = [line.rstrip() for line in match.group(1).strip().splitlines()]
    summary_parts = []
    usage = []
    in_usage = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if set(stripped) <= {"=", "-"} and len(stripped) > 2:
            continue  # title underline
        if stripped.lower().startswith("usage"):
            in_usage = True
            continue
        if in_usage:
            usage.append(stripped)
        elif index > 0 or not summary_parts:
            summary_parts.append(stripped)

    # The first line is the file's title ("Button Component"); the useful
    # summary is what follows it.
    if len(summary_parts) > 1:
        summary = " ".join(summary_parts[1:])
    else:
        summary = " ".join(summary_parts)
    return summary, usage


def parse_file(path: Path, origin: str) -> list:
    """Every macro defined in one component template."""
    text = path.read_text(encoding="utf-8", errors="replace")
    summary, usage = _parse_docblock(text)
    return [
        Component(name, _normalise_args(args), path, summary, usage, origin)
        for name, args in MACRO_RE.findall(text)
    ]


def framework_components_dir() -> Path:
    import feather

    return Path(feather.__file__).parent / "templates" / "components"


def collect(project_dir: Optional[Path] = None) -> list:
    """Framework components, plus a project's own, with overrides applied.

    A component the app defines under ``templates/components/`` with the same
    filename replaces the framework's, which is exactly how Feather's
    template loader resolves it at runtime.
    """
    components = {}

    for path in sorted(framework_components_dir().glob("*.html")):
        if path.stem == "__init__":
            continue
        for component in parse_file(path, "framework"):
            components[(path.stem, component.name)] = component

    if project_dir:
        local = project_dir / "templates" / "components"
        if local.is_dir():
            for path in sorted(local.glob("*.html")):
                for component in parse_file(path, "app"):
                    key = (path.stem, component.name)
                    component.origin = "app (overrides framework)" if key in components else "app"
                    components[key] = component

    return sorted(components.values(), key=lambda c: (c.source.stem, c.name))


def to_markdown(components: list) -> str:
    lines = [
        "# Component Reference",
        "",
        "Generated by `feather components --markdown`. Every macro below is a",
        "server-rendered Jinja2 component: import it, call it, no JavaScript.",
        "",
    ]
    current_file = None
    for component in components:
        if component.source.stem != current_file:
            current_file = component.source.stem
            lines.append(f"## `components/{current_file}.html`")
            lines.append("")
        lines.append(f"### `{component.signature}`")
        lines.append("")
        if component.summary:
            lines.append(component.summary)
            lines.append("")
        lines.append("```jinja")
        lines.append(component.import_line)
        for example in component.usage:
            if example.startswith("{%"):
                continue
            lines.append(example)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


@click.command(name="components")
@click.option("--json", "as_json", is_flag=True, help="Emit the catalogue as JSON.")
@click.option("--markdown", "as_markdown", is_flag=True, help="Emit a Markdown reference.")
@click.option(
    "--output",
    "-o",
    default=None,
    help="Write to this file instead of stdout (use with --markdown).",
)
@click.option("--path", "project_path", default=".", help="Project directory (default: current).")
def components(as_json: bool, as_markdown: bool, output: Optional[str], project_path: str):
    """List the Jinja2 components available to your templates.

    Reads the macros themselves, so the list is always accurate, and shows
    which of your own components override a framework one.

    \b
    Examples:
      feather components                        Print the catalogue
      feather components --json                 Machine-readable
      feather components --markdown -o docs/components.md
    """
    project_dir = Path(project_path).resolve()
    catalogue = collect(project_dir if (project_dir / "app.py").exists() else None)

    if as_json:
        text = json_module.dumps([c.as_dict() for c in catalogue], indent=2)
    elif as_markdown:
        text = to_markdown(catalogue)
    else:
        text = None

    if text is not None:
        if output:
            Path(output).write_text(text + "\n")
            click.echo(f"Wrote {len(catalogue)} components to {output}")
        else:
            click.echo(text)
        return

    current_file = None
    for component in catalogue:
        if component.source.stem != current_file:
            current_file = component.source.stem
            click.echo()
            click.echo(click.style(f"components/{current_file}.html", fg="cyan", bold=True))
        click.echo(f"  {click.style(component.signature, bold=True)}")
        if component.summary:
            click.echo(f"    {component.summary}")
        if component.origin != "framework":
            click.echo(click.style(f"    [{component.origin}]", fg="yellow"))
    click.echo()
    click.echo(f"{len(catalogue)} components")
