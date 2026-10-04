"""Send a few bounded browser-origin GETs to the public readiness route."""

import logging
from urllib.parse import urlsplit

import streamlit as st

from frontend.api_client import get_api_base_url

WAKE_RETRY_DELAYS_MS = (0, 25_000, 75_000)
WAKE_WINDOW_MS = 180_000
logger = logging.getLogger("frontend.wake")
HTML = '<span class="wake-marker" hidden></span>'
JS = """
export default function({ parentElement, data }) {
    const marker = parentElement.querySelector('.wake-marker');
    // Cancel timers from a prior render. Already sent attempts remain recorded
    // for this lifecycle, so remounting cannot send them again.
    if (marker.wakeCleanup) marker.wakeCleanup();
    const storageKey = `backend-wake:${data.attempt}`;
    const read = (key) => {
        try { return sessionStorage.getItem(key); } catch (_) { return null; }
    };
    const write = (key, value) => {
        try { sessionStorage.setItem(key, value); } catch (_) {}
    };
    let startedAt = Number(read(`${storageKey}:started`));
    if (!Number.isFinite(startedAt) || startedAt <= 0) {
        startedAt = Date.now();
        write(`${storageKey}:started`, String(startedAt));
    }
    const timers = [];
    const safeTarget = new URL(data.url);
    console.info(`FRONTEND_BROWSER_WAKE_COMPONENT_MOUNTED target=${safeTarget.host}${safeTarget.pathname}`);

    function sendWake(n) {
        if (!marker.isConnected || Date.now() - startedAt >= data.window_ms) return;
        const sentKey = `${storageKey}:sent:${n}`;
        if (read(sentKey) === '1' || marker.dataset[`sent${n}`] === data.attempt) return;
        // A navigation behaves like opening /ready in a browser tab. It does
        // not need CORS permission, read the response, or transmit complaint data.
        const url = new URL(data.url);
        url.searchParams.set('wake', data.attempt);
        url.searchParams.set('n', String(n));
        const frame = document.createElement('iframe');
        frame.setAttribute('aria-hidden', 'true');
        frame.setAttribute('tabindex', '-1');
        frame.loading = 'eager';
        frame.style.cssText = 'width:1px;height:1px;border:0;position:absolute;left:-9999px;';
        frame.src = url.toString();
        parentElement.appendChild(frame);
        marker.dataset[`sent${n}`] = data.attempt;
        write(sentKey, '1');
        console.info(`FRONTEND_BROWSER_WAKE_REQUEST_START n=${n} target=${url.host}${url.pathname}`);
    }

    data.retry_delays_ms.forEach((delay, n) => {
        if (read(`${storageKey}:sent:${n}`) === '1' || marker.dataset[`sent${n}`] === data.attempt) return;
        const wait = Math.max(0, startedAt + delay - Date.now());
        if (wait === 0) sendWake(n);
        else {
            console.info(`FRONTEND_BROWSER_WAKE_RETRY_SCHEDULED n=${n} delay_ms=${wait}`);
            timers.push(setTimeout(() => sendWake(n), wait));
        }
    });
    const cleanup = () => timers.forEach(clearTimeout);
    marker.wakeCleanup = cleanup;
    return cleanup;
}
"""


def trigger_backend_wake(*, attempt: str) -> None:
    """Mount browser wake requests once per scheduled retry in this attempt."""
    url = get_api_base_url() + "/ready"
    logger.warning(
        "FRONTEND_BROWSER_WAKE_COMPONENT_RENDERED target=%s route=/ready retries_ms=%s",
        urlsplit(url).hostname,
        ",".join(str(delay) for delay in WAKE_RETRY_DELAYS_MS),
    )
    wake = st.components.v2.component("backend_browser_wake", html=HTML, js=JS)
    wake(
        data={
            "url": url,
            "attempt": attempt,
            "retry_delays_ms": WAKE_RETRY_DELAYS_MS,
            "window_ms": WAKE_WINDOW_MS,
        },
        key="backend_browser_wake",
        height=1,
    )
