"""Islands mount once per element.

island() mounts matching elements as soon as an island is registered, and
Feather.init() mounts every [data-island] on DOMContentLoaded. Island scripts
are ES modules, which run before DOMContentLoaded, so without a guard in
init() both paths mounted the same element: init() ran twice and every
data-action fired twice per click.
"""

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATHER_JS = REPO_ROOT / "feather" / "static" / "feather.js"

NODE_HARNESS = textwrap.dedent(
    """
    const fs = require('fs');
    const vm = require('vm');

    const order = process.argv[3];  // 'module-first' or 'late-script'

    function makeIsland(name) {
        const listeners = {};
        return {
            dataset: { island: name },
            addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
            querySelectorAll: () => [],
            querySelector: () => null,
            contains: () => true,
            click(action) {
                const target = { closest: () => ({ dataset: { action } }) };
                (listeners.click || []).forEach((fn) => fn({ target }));
            },
        };
    }

    const el = makeIsland('counter');
    const domListeners = {};
    const sandbox = {
        console,
        localStorage: { getItem: () => null, setItem: () => {} },
        document: {
            querySelectorAll: (selector) =>
                selector === '[data-island]' || selector === '[data-island="counter"]' ? [el] : [],
            addEventListener: (type, fn) => { (domListeners[type] = domListeners[type] || []).push(fn); },
            querySelector: () => null,
        },
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);

    let inits = 0;
    let hits = 0;
    const definition = {
        state: {},
        init() { inits += 1; },
        actions: { hit() { hits += 1; } },
    };
    const domReady = () => (domListeners.DOMContentLoaded || []).forEach((fn) => fn());

    if (order === 'module-first') {
        // An island module runs before DOMContentLoaded, the usual case.
        sandbox.window.island('counter', definition);
        domReady();
    } else {
        // A script loaded after the page was ready.
        domReady();
        sandbox.window.island('counter', definition);
    }
    el.click('hit');

    console.log(JSON.stringify({ inits, hits }));
    """
)


def _run(tmp_path, order):
    harness = tmp_path / "harness.js"
    harness.write_text(NODE_HARNESS)
    result = subprocess.run(["node", str(harness), str(FEATHER_JS), order], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_island_registered_before_dom_ready_mounts_once(tmp_path):
    assert _run(tmp_path, "module-first") == {"inits": 1, "hits": 1}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_island_registered_after_dom_ready_mounts_once(tmp_path):
    assert _run(tmp_path, "late-script") == {"inits": 1, "hits": 1}
