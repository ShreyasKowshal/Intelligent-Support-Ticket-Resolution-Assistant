"""The browser wake component never handles complaint content or readiness state."""

import base64
import shutil
import subprocess

import pytest

from frontend import browser_wake
from frontend.api_client import FrontendError


def test_browser_wake_targets_configured_ready_route(monkeypatch):
    captured = {}

    def register(name, *, html, js):
        captured.update(name=name, html=html, js=js)

        def mount(**kwargs):
            captured.update(kwargs)

        return mount

    monkeypatch.setenv("API_BASE_URL", "https://support-ticket-assistant-api.onrender.com")
    monkeypatch.setattr(browser_wake.st.components.v2, "component", register)
    browser_wake.trigger_backend_wake(attempt="attempt-1")
    assert captured["data"] == {
        "url": "https://support-ticket-assistant-api.onrender.com/ready",
        "attempt": "attempt-1",
        "retry_delays_ms": (0, 25_000, 75_000),
        "window_ms": 180_000,
    }
    assert captured["key"] == "backend_browser_wake"
    assert captured["height"] == 1


def test_browser_wake_uses_bounded_eager_navigations():
    js = browser_wake.JS
    assert browser_wake.WAKE_RETRY_DELAYS_MS == (0, 25_000, 75_000)
    assert browser_wake.WAKE_WINDOW_MS == 180_000
    assert "data.retry_delays_ms.forEach" in js
    assert "setTimeout(() => sendWake(n), wait)" in js
    assert "timers.forEach(clearTimeout)" in js
    assert "Date.now() - startedAt >= data.window_ms" in js
    assert "url.searchParams.set('wake', data.attempt)" in js
    assert "url.searchParams.set('n', String(n))" in js
    assert "frame.loading = 'eager'" in js
    assert "frame.src = url.toString()" in js
    assert "parentElement.appendChild(frame)" in js
    assert "setInterval(" not in js
    assert "fetch(" not in js


def test_browser_wake_retries_and_retry_lifecycle_in_javascript():
    """Exercise the actual component script with a deterministic browser clock."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the browser component test")
    encoded_js = base64.b64encode(browser_wake.JS.encode()).decode()
    harness = """
import assert from 'node:assert/strict';
const { default: mount } = await import('data:text/javascript;base64,ENCODED_JS');
let now = 1000;
let nextTimer = 0;
const timers = new Map();
const stored = new Map();
const frames = [];
Date.now = () => now;
globalThis.setTimeout = (fn, delay) => {
    const id = ++nextTimer;
    timers.set(id, { fn, due: now + delay });
    return id;
};
globalThis.clearTimeout = (id) => timers.delete(id);
globalThis.sessionStorage = {
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => stored.set(key, value),
};
globalThis.document = { createElement: () => ({ setAttribute() {}, style: {} }) };
const marker = { dataset: {}, isConnected: true };
const parentElement = {
    querySelector: () => marker,
    appendChild: (frame) => frames.push(frame.src),
};
const base = {
    url: 'https://support-ticket-assistant-api.onrender.com/ready',
    retry_delays_ms: [0, 25000, 75000], window_ms: 180000,
};
const advance = (to) => {
    while (true) {
        const due = [...timers.entries()]
            .filter(([, timer]) => timer.due <= to)
            .sort((a, b) => a[1].due - b[1].due)[0];
        if (!due) break;
        timers.delete(due[0]);
        now = due[1].due;
        due[1].fn();
    }
    now = to;
};
const data = { ...base, attempt: 'first' };
mount({ parentElement, data });
assert.equal(frames.length, 1);
assert.equal(timers.size, 2);
mount({ parentElement, data }); // Fragment/app remount must not duplicate the first GET.
assert.equal(frames.length, 1);
assert.equal(timers.size, 2);
advance(26000);
assert.equal(frames.length, 2);
mount({ parentElement, data }); // A later remount preserves the remaining retry.
assert.equal(frames.length, 2);
assert.equal(timers.size, 1);
advance(76000);
assert.equal(frames.length, 3);
advance(200000);
assert.equal(frames.length, 3); // No unbounded retry loop.
assert.deepEqual(frames.map((src) => new URL(src).searchParams.get('n')), ['0', '1', '2']);
assert.equal(new Set(frames).size, 3); // Each GET is cache-busted.
assert(frames.every((src) => new URL(src).searchParams.get('wake') === 'first'));
assert(frames.every((src) => new URL(src).pathname === '/ready'));
mount({ parentElement, data: { ...base, attempt: 'retry' } });
assert.equal(frames.length, 4); // Manual Retry gets a fresh lifecycle.
assert.equal(new URL(frames[3]).searchParams.get('wake'), 'retry');
assert.equal(timers.size, 2);
marker.wakeCleanup();
assert.equal(timers.size, 0); // Unmount leaves no timers running.
""".replace("ENCODED_JS", encoded_js)
    completed = subprocess.run(
        [node, "--input-type=module"], input=harness, text=True,
        capture_output=True, timeout=10, check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_browser_wake_carries_no_complaint_or_secret():
    js = browser_wake.JS
    assert "/resolve" not in js
    assert "data.complaint" not in js
    assert "api_key" not in js.lower()
    assert "password" not in js.lower()


def test_browser_wake_does_not_fall_back_to_localhost_on_render(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("API_BASE_URL", raising=False)
    with pytest.raises(FrontendError, match="not configured"):
        browser_wake.trigger_backend_wake(attempt="attempt-1")
