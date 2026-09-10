"""Security: api.js sends the CSRF token only to our own origin.

Runs the real ``feather/static/api.js`` under Node with stubbed browser
globals and records which requests carried ``X-CSRFToken``.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

API_JS = Path(__file__).resolve().parents[2] / "feather" / "static" / "api.js"

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');

const sent = [];
const sandbox = {
  console,
  setTimeout, clearTimeout,
  AbortController,
  URL,
  window: { location: { origin: 'https://app.example', href: 'https://app.example/page' } },
  document: { querySelector: () => ({ content: 'tok-123' }) },
  fetch: async (url, opts) => {
    sent.push({ url, headers: opts.headers || {} });
    return { ok: true, status: 200, json: async () => ({}) };
  },
  XMLHttpRequest: class {
    constructor() { this.headers = {}; this.listeners = {}; this.upload = { addEventListener() {} }; }
    addEventListener(ev, fn) { this.listeners[ev] = fn; }
    open(method, url) { this.url = url; }
    setRequestHeader(k, v) { this.headers[k] = v; }
    send() {
      sent.push({ url: this.url, headers: this.headers, xhr: true });
      this.status = 200; this.responseText = '{}';
      this.listeners.load && this.listeners.load();
    }
  },
};
sandbox.window.document = sandbox.document;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const api = sandbox.window.ApiUtility;
api.defaults.retries = 0;

(async () => {
  await api.post('/api/rel', {});
  await api.post('api/rel-no-slash', {});
  await api.post('https://app.example/api/abs-same', {});
  await api.post('https://evil.example/api/abs-other', {});
  await api.post('//evil.example/api/proto-rel', {});
  await api.post('https://app.example.evil.com/api/prefix', {});
  await api.delete('/api/del');
  await api.get('/api/get');
  await api.upload('/api/up', {}, { onProgress: () => {} });
  await api.upload('https://evil.example/api/up', {}, { onProgress: () => {} });
  await api.upload('/api/up-fetch', {});
  await api.upload('https://evil.example/api/up-fetch', {});
  console.log(JSON.stringify(sent));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_csrf_header_only_goes_to_same_origin():
    proc = subprocess.run(
        ["node", "-e", HARNESS, str(API_JS)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    sent = json.loads(proc.stdout.strip().splitlines()[-1])
    by_url = {s["url"]: s["headers"] for s in sent}

    def has_csrf(url):
        return "X-CSRFToken" in by_url[url]

    # Same-origin state-changing requests carry the token
    assert has_csrf("/api/rel")
    assert has_csrf("api/rel-no-slash")
    assert has_csrf("https://app.example/api/abs-same")
    assert has_csrf("/api/del")
    assert has_csrf("/api/up")
    assert has_csrf("/api/up-fetch")
    assert by_url["/api/rel"]["X-CSRFToken"] == "tok-123"

    # Cross-origin requests never do
    assert not has_csrf("https://evil.example/api/abs-other")
    assert not has_csrf("//evil.example/api/proto-rel")
    assert not has_csrf("https://app.example.evil.com/api/prefix")
    assert not has_csrf("https://evil.example/api/up")
    assert not has_csrf("https://evil.example/api/up-fetch")

    # GET never carries it
    assert not has_csrf("/api/get")

    # Everything else is untouched
    assert by_url["/api/rel"]["Accept"] == "application/json"
    assert by_url["/api/rel"]["Content-Type"] == "application/json"
    assert by_url["https://evil.example/api/abs-other"]["Accept"] == "application/json"
