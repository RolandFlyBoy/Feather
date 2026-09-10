"""Regression tests for 0.9.6 cleanups.

Covers the lazily-resolved prompt modal, streaming `feather db` output,
the removed unreachable stub decorators, corrected docstrings and the
added public exports.
"""

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_MODAL = REPO_ROOT / "feather" / "static" / "prompt-modal.js"


# =============================================================================
# prompt-modal.js resolves its elements lazily
# =============================================================================


NODE_HARNESS = textwrap.dedent(
    """
    const fs = require('fs');
    const vm = require('vm');

    function makeEl(id) {
        const classes = new Set(['hidden']);
        return {
            id,
            value: '',
            placeholder: '',
            textContent: '',
            dataset: {},
            classList: {
                add: (c) => classes.add(c),
                remove: (c) => classes.delete(c),
                contains: (c) => classes.has(c),
            },
            querySelector: () => makeEl(id + '-child'),
            addEventListener: () => {},
            contains: () => true,
            focus: () => {},
            _classes: classes,
        };
    }

    // The modal markup does not exist yet when the script runs (base.html
    // renders it after the scripts).
    let elements = null;

    const sandbox = {
        console,
        setTimeout,
        document: {
            getElementById: (id) => (elements ? elements[id] || null : null),
            addEventListener: () => {},
        },
    };
    sandbox.window = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);

    if (typeof sandbox.window.showPrompt !== 'function') {
        console.log(JSON.stringify({ ok: false, reason: 'showPrompt missing' }));
        process.exit(0);
    }

    // Markup appears afterwards.
    elements = {
        'prompt-modal': makeEl('prompt-modal'),
        'prompt-title': makeEl('prompt-title'),
        'prompt-message': makeEl('prompt-message'),
        'prompt-input': makeEl('prompt-input'),
    };

    sandbox.window.showPrompt({ title: 'T', message: 'M', onConfirm: () => {} });

    console.log(JSON.stringify({
        ok: true,
        visible: !elements['prompt-modal']._classes.has('hidden'),
        title: elements['prompt-title'].textContent,
    }));
    """
)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_prompt_modal_works_when_markup_loads_after_the_script(tmp_path):
    """showPrompt must look its elements up at call time, not at load time."""
    harness = tmp_path / "harness.js"
    harness.write_text(NODE_HARNESS)

    result = subprocess.run(
        ["node", str(harness), str(PROMPT_MODAL)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"], payload
    assert payload["visible"] is True
    assert payload["title"] == "T"


def test_prompt_modal_has_no_load_time_element_lookup():
    """No getElementById before showPrompt is defined."""
    source = PROMPT_MODAL.read_text()

    first_lookup = source.index("getElementById")
    show_prompt = source.index("window.showPrompt")
    assert first_lookup > show_prompt


# =============================================================================
# feather db streams subprocess output
# =============================================================================


def test_db_commands_do_not_capture_output():
    """`feather db upgrade` should stream migration output live."""
    source = (REPO_ROOT / "feather" / "cli" / "db.py").read_text()
    flask_db_section = source[: source.index("def seed")]

    assert "capture_output=True" not in flask_db_section


# =============================================================================
# Dead code removal
# =============================================================================


def test_no_stub_auth_decorators():
    """core.decorators re-exports the real auth decorators, no stubs."""
    import feather.auth.decorators as auth_decorators
    import feather.core.decorators as core_decorators

    assert core_decorators.admin_required is auth_decorators.admin_required
    assert core_decorators.role_required is auth_decorators.role_required

    source = (REPO_ROOT / "feather" / "core" / "decorators.py").read_text()
    assert "Stub decorator - auth module not initialized" not in source


def test_dispatcher_docstrings_do_not_claim_missing_features():
    """Async listeners are implemented; the docs must not say otherwise."""
    source = (REPO_ROOT / "feather" / "events" / "dispatcher.py").read_text()
    assert "not yet implemented" not in source


def test_package_docstring_has_no_dangling_doc_reference():
    source = (REPO_ROOT / "feather" / "__init__.py").read_text()
    assert "feather_framework.md" not in source
    assert "http://localhost:5000 in your browser" not in source


# =============================================================================
# Public exports
# =============================================================================


@pytest.mark.parametrize(
    "name",
    [
        "htmx_redirect",
        "with_trigger",
        "AccountSuspendedError",
        "AccountPendingError",
        "RateLimitError",
    ],
)
def test_new_exports_are_available(name):
    import feather

    assert name in feather.__all__
    assert getattr(feather, name) is not None


def test_existing_exports_are_kept():
    import feather

    for name in (
        "Feather",
        "api",
        "page",
        "inject",
        "auth_required",
        "csrf_exempt",
        "Service",
        "db",
        "Model",
        "dispatch",
        "listen",
        "get_queue",
        "job",
        "scheduled",
        "ValidationError",
        "NotFoundError",
    ):
        assert name in feather.__all__
