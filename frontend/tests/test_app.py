"""Exercise the actual Streamlit page against a local fake-provider API."""

import json
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
import uvicorn
import streamlit as st
from sqlalchemy.engine import URL
from streamlit.testing.v1 import AppTest

import frontend.api_client as api_client
from frontend import browser_wake, live_complaint

ORIGINAL_CHECK_BACKEND_READINESS = api_client.check_backend_readiness

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api_service import ApiServices
from app.gemini_client import GeminiProviderError
from app.main import create_app
from app.search import SearchResults, SemanticSearch
from app.seed import seed_database
from app.storage import Repository

COMPLAINTS = [
    ("My broadband drops every evening around 8 PM and I already restarted the router twice.",
     "broadband_connectivity"),
    ("I was charged an extra fee this month and I don't know why.", "billing_dispute"),
    ("Calls work but my mobile internet does not.", "mobile_data"),
    ("My fiber modem shows a red optical signal alarm after a storm, and no service works.", "other"),
]


class DemoEncoder:
    dimension = 4

    def encode(self, texts):
        vectors = []
        for text in texts:
            lower = text.lower()
            if any(word in lower for word in ("billing_dispute", "charged", "extra fee")):
                vectors.append([0.0, 1.0, 0.0, 0.0])
            elif any(word in lower for word in ("mobile_data", "mobile internet", "calls work")):
                vectors.append([0.0, 0.0, 1.0, 0.0])
            elif any(word in lower for word in ("broadband_connectivity", "broadband drops")):
                vectors.append([1.0, 0.0, 0.0, 0.0])
            else:
                vectors.append([0.5, 0.5, 0.5, 0.5])
        return np.asarray(vectors, dtype=np.float32)


class DemoProvider:
    def generate_analysis(self, _instruction, complaint):
        lower = complaint.lower()
        if "providererror" in lower:
            raise GeminiProviderError("private provider detail")
        if "charged" in lower:
            category, product, severity = "billing_dispute", "mobile_postpaid", "MEDIUM"
        elif "mobile internet" in lower:
            category, product, severity = "mobile_data", "mobile_prepaid", "MEDIUM"
        elif "optical signal" in lower:
            category, product, severity = "optical_signal_fault", "broadband", "HIGH"
        else:
            category, product, severity = "broadband_connectivity", "broadband", "HIGH"
        return {
            "intent": "restore or explain service", "category": category, "product": product,
            "severity": severity, "sentiment": "FRUSTRATED", "confidence": 0.8,
            "needs_review": False, "rationale": "The complaint describes a telecom service issue.",
        }

    def generate_resolution(self, _instruction, context):
        source_id = json.loads(context)["retrieved_evidence"][0]["source_id"]
        return {
            "problem_summary": "The complaint needs a support check.",
            "resolution_steps": [{
                "step_number": 1, "action": "Review approved guidance and verify the service state.",
                "source_ids": [source_id],
            }],
            "escalation_recommendation": "Escalate if the issue persists.",
            "confidence_or_evidence_note": "Based on retrieved approved evidence.",
            "sources_used": [source_id], "insufficient_evidence": False,
        }


@pytest.fixture
def local_api(tmp_path, monkeypatch):
    repository = Repository(URL.create("sqlite", database=str(tmp_path / "support.db")))
    seed_database(repository)
    search = SemanticSearch(repository, DemoEncoder(), tmp_path / "indexes")
    normal_search = search.search

    def demo_search(complaint, *args, **kwargs):
        if "noevidence" in complaint.lower():
            return SearchResults([], [])
        return normal_search(complaint, *args, **kwargs)

    search.search = demo_search
    service = ApiServices(repository, search, DemoProvider())
    app = create_app(lambda: service)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        assert server.started
        base_url = f"http://127.0.0.1:{port}"
        monkeypatch.setenv("API_BASE_URL", base_url)
        with httpx.Client(base_url=base_url) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def submit(complaint):
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    set_complaint(page, complaint)
    page.get_by_key("submit_complaint").click().run(timeout=30)
    assert not page.exception
    return page


def status_is(page, label):
    return any(label in item.value for item in page.markdown)


def set_complaint(page, complaint):
    """Commit the native textarea's value as Streamlit does on blur/Ctrl+Enter."""
    return page.text_area[0].set_value(complaint).run(timeout=30)


def complaint_value(page):
    return page.text_area[0].value


@pytest.fixture(autouse=True)
def app_test_input(monkeypatch):
    """AppTest has no browser event loop for Components v2; exercise the Python page."""
    monkeypatch.setattr(api_client, "check_backend_readiness", lambda **_: "ready")
    monkeypatch.setattr(browser_wake, "trigger_backend_wake", lambda **_: None)

    def render(*, ready, initial_value, ack):
        complaint = st.text_area("Customer complaint", key="complaint")
        st.caption(f"{len(complaint)} / {api_client.MAX_COMPLAINT_LENGTH} characters")
        if len(complaint) > api_client.MAX_COMPLAINT_LENGTH:
            st.error("Complaint must be 3000 characters or fewer.")
        if st.button(
            "Analyze & Resolve", key="submit_complaint", type="primary",
            disabled=not ready or not complaint.strip() or len(complaint) > api_client.MAX_COMPLAINT_LENGTH,
        ):
            return {"complaint": complaint, "id": f"test-{time.monotonic_ns()}"}
        return None

    monkeypatch.setattr(live_complaint, "complaint_input", render)


@pytest.mark.parametrize(
    ("state", "label", "disabled"),
    [("ready", "Backend ready", False), ("starting", "Starting backend", True),
     ("unavailable", "Backend unavailable", True)],
)
def test_status_text_is_rendered_for_every_backend_state(monkeypatch, state, label, disabled):
    monkeypatch.setattr(api_client, "check_backend_readiness", lambda **_: state)
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert any("backend-status" in item.value and label in item.value for item in page.markdown)
    set_complaint(page, "My broadband is down.")
    assert page.get_by_key("submit_complaint").disabled is disabled


def test_ready_status_enables_submission_and_does_not_resolve(local_api, monkeypatch):
    calls = []
    original = api_client.resolve_complaint
    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(api_client, "resolve_complaint", counted)
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert status_is(page, "🟢 Backend ready")
    set_complaint(page, COMPLAINTS[0][0])
    assert not page.get_by_key("submit_complaint").disabled
    assert calls == []


def test_initial_load_triggers_browser_wake_and_readiness_without_resolve(monkeypatch):
    wakes, checks = [], []
    monkeypatch.setattr(browser_wake, "trigger_backend_wake", lambda *, attempt: wakes.append(attempt))
    monkeypatch.setattr(api_client, "check_backend_readiness", lambda **_: checks.append(1) or "ready")
    monkeypatch.setattr(api_client, "resolve_complaint", lambda *_: pytest.fail("wake called resolve"))
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert len(wakes) == 1
    assert checks == [1]
    assert status_is(page, "🟢 Backend ready")


def test_hosted_missing_backend_url_fails_closed(monkeypatch, caplog):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.setattr(browser_wake, "trigger_backend_wake", lambda **_: pytest.fail("wake without URL"))
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert status_is(page, "🔴 Backend unavailable")
    assert page.get_by_key("submit_complaint").disabled
    assert "FRONTEND_WAKE_CONFIG_ERROR" in caplog.text


def test_starting_backend_keeps_one_attempt_during_editing(monkeypatch):
    wakes, checks = [], []
    monkeypatch.setattr(browser_wake, "trigger_backend_wake", lambda *, attempt: wakes.append(attempt))
    monkeypatch.setattr(api_client, "check_backend_readiness", lambda **_: checks.append(1) or "starting")
    monkeypatch.setattr(api_client, "resolve_complaint", lambda *_: pytest.fail("startup called resolve"))
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    started = page.session_state["backend_started_at"]
    attempt = page.session_state["backend_wake_attempt"]
    set_complaint(page, "My broadband has a problem.")
    set_complaint(page, "My broadband was down.")
    assert complaint_value(page) == "My broadband was down."
    assert page.get_by_key("submit_complaint").disabled
    assert page.session_state["backend_started_at"] == started
    assert page.session_state["backend_wake_attempt"] == attempt
    assert checks == [1]
    assert set(wakes) == {attempt}


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_failures_stay_yellow(monkeypatch, status):
    transport = api_client.httpx.MockTransport(lambda _: api_client.httpx.Response(status))
    check = ORIGINAL_CHECK_BACKEND_READINESS
    monkeypatch.setattr(api_client, "check_backend_readiness",
                        lambda **_: check(transport=transport))
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert status_is(page, "🟡 Starting backend...")
    assert page.get_by_key("submit_complaint").disabled


def test_pending_then_ready_preserves_complaint(monkeypatch):
    state = {"value": "starting"}
    wakes = []
    monkeypatch.setattr(api_client, "check_backend_readiness", lambda **_: state["value"])
    monkeypatch.setattr(browser_wake, "trigger_backend_wake", lambda *, attempt: wakes.append(attempt))
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    set_complaint(page, "My broadband is down.")
    assert status_is(page, "🟡 Starting backend...")
    state["value"] = "ready"
    page.session_state["backend_next_check_at"] = 0.0
    page.run(timeout=30)
    assert status_is(page, "🟢 Backend ready")
    assert not page.get_by_key("submit_complaint").disabled
    assert complaint_value(page) == "My broadband is down."
    assert len(set(wakes)) == 1


def test_window_expires_red_and_retry_refreshes_wake_attempt(monkeypatch):
    state = {"value": "starting"}
    wakes = []
    monkeypatch.setattr(api_client, "check_backend_readiness", lambda **_: state["value"])
    monkeypatch.setattr(browser_wake, "trigger_backend_wake", lambda *, attempt: wakes.append(attempt))
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    first_attempt = page.session_state["backend_wake_attempt"]
    set_complaint(page, "My broadband is down.")
    page.session_state["backend_started_at"] = time.monotonic() - 181
    page.run(timeout=30)
    assert status_is(page, "🔴 Backend unavailable")
    assert page.get_by_key("submit_complaint").disabled
    page.get_by_key("retry_backend_connection").click().run(timeout=30)
    assert status_is(page, "🟡 Starting backend...")
    assert page.session_state["backend_wake_attempt"] != first_attempt
    assert len(set(wakes)) == 2
    state["value"] = "ready"
    page.session_state["backend_next_check_at"] = 0.0
    page.run(timeout=30)
    assert status_is(page, "🟢 Backend ready")
    assert complaint_value(page) == "My broadband is down."


def test_editing_does_not_explicitly_rerun_or_resolve(local_api, monkeypatch):
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert status_is(page, "🟢 Backend ready")
    monkeypatch.setattr(st, "rerun", lambda: pytest.fail("editing explicitly reran the page"))
    monkeypatch.setattr(api_client, "resolve_complaint", lambda *_: pytest.fail("editing called resolve"))
    set_complaint(page, "My broadband is down.")
    assert complaint_value(page) == "My broadband is down."
    assert not page.get_by_key("submit_complaint").disabled
    set_complaint(page, "  ")
    assert page.get_by_key("submit_complaint").disabled
    assert not page.exception


def test_one_click_makes_one_resolve_call_even_after_rerun(local_api, monkeypatch):
    calls = []
    original = api_client.resolve_complaint
    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(api_client, "resolve_complaint", counted)
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    set_complaint(page, COMPLAINTS[0][0])
    page.get_by_key("submit_complaint").click().run(timeout=30)
    page.run(timeout=30)
    assert len(calls) == 1
    assert page.header


def test_connection_loss_restarts_status_without_resubmitting(monkeypatch):
    state = {"value": "ready"}
    monkeypatch.setattr(api_client, "check_backend_readiness", lambda **_: state["value"])
    calls = []
    def connection_lost(_complaint):
        calls.append("resolve")
        state["value"] = "starting"
        raise api_client.BackendConnectionError("Backend is starting. Please wait until the status changes to Ready.")
    monkeypatch.setattr(api_client, "resolve_complaint", connection_lost)
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    first_attempt = page.session_state["backend_wake_attempt"]
    set_complaint(page, "My broadband is down.")
    page.get_by_key("submit_complaint").click().run(timeout=30)
    assert status_is(page, "🟡 Starting backend...")
    assert page.get_by_key("submit_complaint").disabled
    assert calls == ["resolve"]
    assert page.session_state["backend_wake_attempt"] != first_attempt


def test_four_demo_complaints_show_all_sections_and_citations(local_api):
    for complaint, expected_category in COMPLAINTS:
        page = submit(complaint)
        assert [item.value for item in page.header] == [
            "1. Complaint Analysis", "2. Similar Resolved Tickets",
            "3. Relevant Knowledge Base Articles", "4. Resolution Draft",
            "5. Sources Used", "6. System Information",
        ]
        assert page.metric[0].value == expected_category
        assert len(page.expander) >= 2
        assert any(item.value.startswith("Citations: ") for item in page.caption)
        assert any("verify every step against current KB guidance" in item.value for item in page.warning)
        assert any("Backend processing time" in item.value for item in page.caption)
        if expected_category == "other":
            assert any("Agent review required" in item.value for item in page.warning)


def test_insufficient_evidence_has_no_confident_steps(local_api):
    page = submit("noevidence My broadband service has an unfamiliar failure.")
    assert any("Insufficient evidence" in item.value for item in page.warning)
    assert any("Agent review required" in item.value for item in page.warning)
    assert not any(item.value.startswith("Citations: ") for item in page.caption)
    assert any("No sources were cited" in item.value for item in page.info)


def test_provider_error_is_cleanly_displayed(local_api):
    page = submit("providererror My broadband has stopped working.")
    assert any("AI provider is unavailable" in item.value for item in page.error)
    assert not page.header
    assert "private provider detail" not in str([item.value for item in page.error])


def test_sample_controls_are_absent(local_api):
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert not page.sidebar.button
    assert len(page.button) == 1
    assert complaint_value(page) == ""
    assert not page.header


def test_complaint_counter_and_input_validation(local_api):
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    assert page.get_by_key("submit_complaint").disabled
    assert any("0 / 3000 characters" in item.value for item in page.caption)
    set_complaint(page, "   ")
    assert page.get_by_key("submit_complaint").disabled
    set_complaint(page, "a" * 3000)
    assert any("3000 / 3000 characters" in item.value for item in page.caption)
    assert not page.get_by_key("submit_complaint").disabled
    set_complaint(page, "a" * 3001)
    assert complaint_value(page) == "a" * 3001
    assert any("3001 / 3000 characters" in item.value for item in page.caption)
    assert any("Complaint must be 3000 characters or fewer" in item.value for item in page.error)
    assert page.get_by_key("submit_complaint").disabled


def test_app_test_input_validation_when_editing_and_clearing(local_api):
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    set_complaint(page, "h")
    assert any("1 / 3000 characters" in item.value for item in page.caption)
    assert not page.get_by_key("submit_complaint").disabled
    set_complaint(page, "hello")
    assert any("5 / 3000 characters" in item.value for item in page.caption)
    set_complaint(page, "")
    assert any("0 / 3000 characters" in item.value for item in page.caption)
    assert page.get_by_key("submit_complaint").disabled


def test_non_actionable_input_shows_clarification_without_evidence(local_api):
    page = submit("😂")
    assert [item.value for item in page.header] == ["1. Complaint Analysis"]
    assert not page.expander
    assert any("No clear telecom issue was identified" in item.value for item in page.info)
    assert any("Retrieval and resolution drafting were intentionally skipped" in item.value
               for item in page.caption)
    assert not any(item.value.startswith("Citations: ") for item in page.caption)


def test_new_submission_replaces_previous_recommendation(local_api):
    page = submit(COMPLAINTS[0][0])
    assert page.header
    set_complaint(page, COMPLAINTS[1][0])
    page.get_by_key("submit_complaint").click().run(timeout=30)
    assert page.metric[0].value == COMPLAINTS[1][1]
    assert complaint_value(page) == COMPLAINTS[1][0]
