"""A single bounded worker owns every cold-start retry for one session."""

from threading import Event
from time import monotonic

import httpx

from frontend import api_client
from frontend import wake


def test_wake_request_remains_pending_until_ready_responds(monkeypatch):
    entered = Event()
    release = Event()
    observed = []

    def delayed_ready(*, read_timeout):
        observed.append(read_timeout)
        entered.set()
        assert release.wait(timeout=5)
        return "ready"

    monkeypatch.setattr(wake, "wake_backend_readiness", delayed_ready)
    future = wake.launch_backend_wake(deadline=monotonic() + 120, retry_interval=5)
    try:
        assert entered.wait(timeout=2)
        assert not future.done()
    finally:
        release.set()
    assert future.result(timeout=2) == "ready"
    assert observed == [115.0]


def test_two_502_results_retry_inside_one_worker(monkeypatch, caplog):
    monkeypatch.setenv("API_BASE_URL", "https://support-ticket-assistant-api.onrender.com")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if len(calls) < 3:
            return httpx.Response(502)
        return httpx.Response(200, json={
            "status": "ready", "database": True, "search_index": True,
            "embedding_model": True, "gemini_configured": True,
        })

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        wake, "wake_backend_readiness",
        lambda *, read_timeout: api_client.wake_backend_readiness(
            read_timeout=read_timeout, transport=transport,
        ),
    )
    future = wake.launch_backend_wake(deadline=monotonic() + 5.06, retry_interval=0.01)
    assert future.result(timeout=2) == "ready"
    assert calls == ["/ready", "/ready", "/ready"]
    assert caplog.text.count("FRONTEND_WAKE_REQUEST_STATUS=502") == 2
    assert caplog.text.count("FRONTEND_WAKE_WORKER_CREATED") == 1
    assert caplog.text.count("FRONTEND_WAKE_WORKER_STARTED") == 1


def test_repeated_transient_failures_stop_at_deadline(monkeypatch, caplog):
    calls = []

    def starting(*, read_timeout):
        calls.append(read_timeout)
        return "starting"

    monkeypatch.setattr(wake, "wake_backend_readiness", starting)
    future = wake.launch_backend_wake(deadline=monotonic() + 5.06, retry_interval=0.01)
    assert future.result(timeout=2) == "unavailable"
    assert future.done()
    assert len(calls) >= 2
    assert caplog.text.count("FRONTEND_WAKE_WORKER_CREATED") == 1
    assert "FRONTEND_WAKE_STARTUP_WINDOW_EXPIRED" in caplog.text


def test_wake_worker_sanitizes_unexpected_failure(monkeypatch, caplog):
    def failure(*, read_timeout):
        raise RuntimeError("private internal detail")

    monkeypatch.setattr(wake, "wake_backend_readiness", failure)
    future = wake.launch_backend_wake(deadline=monotonic() + 120, retry_interval=5)
    assert future.result(timeout=2) == "unavailable"
    assert "FRONTEND_WAKE_WORKER_EXCEPTION=RuntimeError" in caplog.text
    assert "private internal detail" not in caplog.text
