"""The browser wake component never handles complaint content or readiness state."""

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
    }
    assert captured["key"] == "backend_browser_wake"
    assert captured["height"] == 1


def test_browser_wake_is_one_eager_navigation_per_attempt():
    js = browser_wake.JS
    assert "marker.dataset.attempt === data.attempt" in js
    assert "sessionStorage.getItem(storageKey)" in js
    assert "sessionStorage.setItem(storageKey, '1')" in js
    assert "frame.loading = 'eager'" in js
    assert "frame.src = data.url" in js
    assert "parentElement.appendChild(frame)" in js
    assert "fetch(" not in js


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
