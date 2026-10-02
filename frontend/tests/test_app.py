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
from sqlalchemy.engine import URL
from streamlit.testing.v1 import AppTest

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
    page.text_area[0].set_value(complaint)
    page.button[0].click().run(timeout=30)
    assert not page.exception
    return page


def test_four_demo_complaints_show_all_sections_and_citations(local_api):
    for complaint, expected_category in COMPLAINTS:
        page = submit(complaint)
        assert [item.value for item in page.header] == [
            "1. Complaint Analysis", "2. Similar Resolved Tickets",
            "3. Relevant Knowledge Base Articles", "4. Recommended Resolution",
            "5. Sources Used", "6. System Information",
        ]
        assert page.metric[0].value == expected_category
        assert len(page.expander) >= 2
        assert any(item.value.startswith("Citations: ") for item in page.caption)
        assert any("Backend processing time" in item.value for item in page.caption)
        if expected_category == "other":
            assert any("Agent review required" in item.value for item in page.warning)


def test_insufficient_evidence_has_no_confident_steps(local_api):
    page = submit("noevidence My broadband service has an unfamiliar failure.")
    assert any("Insufficient evidence" in item.value for item in page.warning)
    assert not any(item.value.startswith("Citations: ") for item in page.caption)
    assert any("No sources were cited" in item.value for item in page.info)


def test_provider_error_is_cleanly_displayed(local_api):
    page = submit("providererror My broadband has stopped working.")
    assert any("AI provider is unavailable" in item.value for item in page.error)
    assert not page.header
    assert "private provider detail" not in str([item.value for item in page.error])


def test_sample_selection_populates_complaint_without_submitting(local_api):
    page = AppTest.from_file(str(ROOT / "frontend" / "app.py")).run(timeout=30)
    page.sidebar.button[0].click().run(timeout=30)
    assert page.text_area[0].value == COMPLAINTS[0][0]
    assert not page.header
    page.button[0].click().run(timeout=30)
    assert page.metric[0].value == "broadband_connectivity"


def test_editing_complaint_clears_previous_recommendation(local_api):
    page = submit(COMPLAINTS[0][0])
    assert page.header
    page.text_area[0].set_value(COMPLAINTS[1][0]).run(timeout=30)
    assert not page.header
    assert page.text_area[0].value == COMPLAINTS[1][0]
