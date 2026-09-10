"""Files that make a scaffolded app legible to AI coding assistants.

A scaffolded app already gets a ``CLAUDE.md``. Two things were missing.

The first is that its rules were prose, so an assistant had no way to check
its own work: ``feather check`` now turns each rule into a check, and this
module makes sure the generated guidance says so.

The second is that the guidance was Claude-specific. ``AGENTS.md`` is the
vendor-neutral name other tools look for, so the scaffold writes both with
the same body, generated together so a given app's two files always agree.
Both carry the full rules rather than one pointing at the other: an
assistant that has to follow a link to find the rules often does not.
"""

import json

#: Commands an assistant should be able to run without stopping to ask. They
#: are all read-only or test-only; nothing here writes to a database or
#: touches the network.
SAFE_COMMANDS = [
    "Bash(feather check)",
    "Bash(feather check:*)",
    "Bash(feather components)",
    "Bash(feather components:*)",
    "Bash(feather routes)",
    "Bash(feather routes:*)",
    "Bash(feather security-check)",
    "Bash(feather security-check:*)",
    "Bash(feather test)",
    "Bash(feather test:*)",
    "Bash(pytest)",
    "Bash(pytest:*)",
    "Bash(git status)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
]


def render_agents_md(body: str) -> str:
    """Wrap the generated guidance with the machine-checkable preamble."""
    return f"""{body}

## Checking your work

The rules above are not suggestions in a document; most of them are checked.

```bash
feather check              # conventions: inline styles, native dialogs, raw fetch, route auth
feather check --json       # same findings, machine-readable
feather security-check     # secrets, cookies, debug settings, dependency versions
feather test               # the project's own tests
```

`feather check` exits non-zero when it finds an error, so run it before you
say a change is finished. It reports the file and line, and a remedy for
each finding.

## Finding the components

Do not guess a component's arguments, and do not rely on this file listing
them. Ask:

```bash
feather components         # every macro, with its signature and import line
feather components --json  # machine-readable
```

The catalogue is parsed from the macros themselves, so it is accurate even
when this document is not. Components your app defines under
`templates/components/` appear alongside the framework's, marked as
overrides.

## Where things live

```bash
feather routes             # every registered route, its methods and endpoint
```

When a route seems to be missing, that command is the fastest answer. Since
0.9.6 an import error in a discovered module fails startup loudly instead of
dropping the module silently, so a route that is absent from this list is
usually a missing decorator rather than a typo.
"""


def render_claude_settings() -> str:
    """`.claude/settings.json` allowing the read-only commands."""
    return json.dumps(
        {
            "permissions": {
                "allow": SAFE_COMMANDS,
            }
        },
        indent=2,
    )


def agent_files(app_name: str, claude_md_body: str) -> dict:
    """Return {relative path: content} for the AI-guidance files.

    CLAUDE.md and AGENTS.md get the same body. They are written from one
    source in one pass, so a generated app's two files always agree.
    """
    guidance = render_agents_md(claude_md_body)
    return {
        "CLAUDE.md": guidance,
        "AGENTS.md": guidance,
        ".claude/settings.json": render_claude_settings(),
    }
