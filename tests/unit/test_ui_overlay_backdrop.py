"""Dialogs and the lightbox close on a backdrop click, not at the end of a drag.

A click whose press and release land on different elements is dispatched to
their nearest common ancestor. Pressing inside a dialog's content and
releasing over the backdrop therefore reports a click whose target is the
<dialog> itself, which is what the backdrop check looked for, so the dialog
closed part way through dragging a slider, selecting text or panning a map.
An overlay now closes only when the press and the release are both on the
backdrop.
"""

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_JS = REPO_ROOT / "feather" / "static" / "ui.js"

NODE_HARNESS = textwrap.dedent(
    """
    const fs = require('fs');
    const vm = require('vm');

    function makeEl({ classes = [], children = {}, all = {} } = {}) {
        const listeners = {};
        const attrs = {};
        const classSet = new Set(classes);
        const el = {
            dataset: {}, style: {}, hidden: false, textContent: '',
            classList: {
                contains: (c) => classSet.has(c),
                add: (c) => classSet.add(c),
                toggle: (c, on) => (on ? classSet.add(c) : classSet.delete(c)),
            },
            setAttribute: (k, v) => { attrs[k] = String(v); },
            getAttribute: (k) => (k in attrs ? attrs[k] : null),
            hasAttribute: (k) => k in attrs,
            removeAttribute: (k) => { delete attrs[k]; },
            addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
            querySelector: (s) => children[s] || null,
            querySelectorAll: (s) => all[s] || [],
            showModal() { attrs.open = ''; },
            close() { delete attrs.open; (listeners.close || []).forEach((fn) => fn({})); },
            fire(type, event) { (listeners[type] || []).forEach((fn) => fn(event)); },
            get isOpen() { return 'open' in attrs; },
        };
        return el;
    }

    // A pointer gesture as a browser dispatches it: pointerdown on the press
    // target, pointerup on the release target, then one click on the nearest
    // element containing both (the overlay itself when they differ).
    function gesture(overlay, pressOn, releaseOn) {
        overlay.fire('pointerdown', { target: pressOn });
        overlay.fire('pointerup', { target: releaseOn });
        overlay.fire('click', { target: pressOn === releaseOn ? pressOn : overlay });
    }

    // ── A .ui-dialog ──────────────────────────────────────────
    const content = makeEl();
    const closeButton = makeEl();
    const dialog = makeEl({ classes: ['ui-dialog'], all: { '[data-dialog-close]': [closeButton] } });

    // ── The lightbox, created by ui.js on first use ───────────
    const frame = makeEl({ classes: ['ui-lightbox-frame'] });
    const image = makeEl();
    const lightboxChildren = {
        '.ui-lightbox-frame': frame, img: image, '.ui-lightbox-caption': makeEl(),
        '.ui-lightbox-close': makeEl(), '.ui-lightbox-prev': makeEl(), '.ui-lightbox-next': makeEl(),
    };
    let lightbox = null;
    const link = makeEl();
    link.setAttribute('data-lightbox', 'album');
    link.setAttribute('href', 'photo.jpg');

    const document = {
        readyState: 'complete',
        body: { style: {}, addEventListener: () => {}, appendChild: () => {} },
        addEventListener: () => {},
        getElementById: (id) => (id === 'ui-lightbox' ? lightbox : null),
        createElement: () => (lightbox = makeEl({ children: lightboxChildren })),
        querySelectorAll: (s) => {
            if (s === 'dialog.ui-dialog:not([data-ui-wired])') return [dialog];
            if (s === '[data-lightbox]:not([data-ui-wired])' || s === '[data-lightbox="album"]') return [link];
            return [];
        },
    };
    const sandbox = { console, document, window: {} };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);

    const results = {};
    function check(name, overlay, open, pressOn, releaseOn) {
        open();
        gesture(overlay, pressOn, releaseOn);
        results[name] = overlay.isOpen ? 'open' : 'closed';
    }
    const openDialog = () => dialog.showModal();
    const openLightbox = () => link.fire('click', { preventDefault() {} });

    check('dialog_backdrop_click', dialog, openDialog, dialog, dialog);
    check('dialog_drag_out_of_content', dialog, openDialog, content, dialog);
    check('dialog_drag_into_content', dialog, openDialog, dialog, content);
    check('dialog_click_in_content', dialog, openDialog, content, content);
    openDialog(); closeButton.fire('click', {}); results.dialog_close_button = dialog.isOpen ? 'open' : 'closed';

    openLightbox();
    check('lightbox_frame_click', lightbox, openLightbox, frame, frame);
    check('lightbox_backdrop_click', lightbox, openLightbox, lightbox, lightbox);
    check('lightbox_drag_out_of_image', lightbox, openLightbox, image, lightbox);
    check('lightbox_drag_into_image', lightbox, openLightbox, lightbox, image);

    console.log(JSON.stringify(results));
    """
)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_overlays_close_on_backdrop_clicks_but_not_at_the_end_of_a_drag(tmp_path):
    harness = tmp_path / "harness.js"
    harness.write_text(NODE_HARNESS)
    result = subprocess.run(["node", str(harness), str(UI_JS)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "dialog_backdrop_click": "closed",
        "dialog_drag_out_of_content": "open",
        "dialog_drag_into_content": "open",
        "dialog_click_in_content": "open",
        "dialog_close_button": "closed",
        "lightbox_frame_click": "closed",
        "lightbox_backdrop_click": "closed",
        "lightbox_drag_out_of_image": "open",
        "lightbox_drag_into_image": "open",
    }
