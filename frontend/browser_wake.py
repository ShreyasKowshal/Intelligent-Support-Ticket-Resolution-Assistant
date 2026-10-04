"""Trigger one browser-origin GET to the public backend readiness route."""

import streamlit as st

from frontend.api_client import get_api_base_url

HTML = '<span class="wake-marker" hidden></span>'
JS = """
export default function({ parentElement, data }) {
    const marker = parentElement.querySelector('.wake-marker');
    if (marker.dataset.attempt === data.attempt) return;
    marker.dataset.attempt = data.attempt;
    const storageKey = `backend-wake:${data.attempt}`;
    try { if (sessionStorage.getItem(storageKey)) return; } catch (_) {}

    // A navigation behaves like opening /ready in a browser tab. It does not
    // need CORS permission, read the response, or transmit complaint data.
    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.setAttribute('tabindex', '-1');
    frame.loading = 'eager';
    frame.style.cssText = 'width:1px;height:1px;border:0;position:absolute;left:-9999px;';
    frame.src = data.url;
    parentElement.appendChild(frame);
    try { sessionStorage.setItem(storageKey, '1'); } catch (_) {}
}
"""


def trigger_backend_wake(*, attempt: str) -> None:
    """Mount a tiny component; its browser makes one harmless GET per attempt."""
    wake = st.components.v2.component("backend_browser_wake", html=HTML, js=JS)
    wake(data={"url": get_api_base_url() + "/ready", "attempt": attempt},
         key="backend_browser_wake", height=1)
