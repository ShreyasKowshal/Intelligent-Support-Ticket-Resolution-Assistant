"""Background wake requests must never block a Streamlit script run."""

from threading import Event

from frontend import wake


def test_wake_request_remains_pending_until_health_responds(monkeypatch):
    entered = Event()
    release = Event()
    observed = []

    def delayed_health(*, read_timeout):
        observed.append(read_timeout)
        entered.set()
        assert release.wait(timeout=5)
        return "alive"

    monkeypatch.setattr(wake, "check_backend_health", delayed_health)
    future = wake.launch_backend_wake(read_timeout=115.0)
    try:
        assert entered.wait(timeout=2)
        assert not future.done()
    finally:
        release.set()
    assert future.result(timeout=2) == "alive"
    assert observed == [115.0]


def test_wake_worker_sanitizes_unexpected_failure(monkeypatch):
    def failure(*, read_timeout):
        raise RuntimeError("private internal detail")

    monkeypatch.setattr(wake, "check_backend_health", failure)
    assert wake.launch_backend_wake(read_timeout=115.0).result(timeout=2) == "starting"
