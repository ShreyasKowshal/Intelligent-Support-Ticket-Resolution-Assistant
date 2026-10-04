"""HTTP contracts and orchestration use local fakes, never Gemini quota."""

import hashlib
from datetime import datetime, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from app.api_service import ApiServices
from app.gemini_client import GeminiProviderError
from app.llm import FakeLLMClient
from app.main import create_app
from app.search import SearchResults, SemanticSearch
from app.seed import seed_database
from app.storage import Repository

COMPLAINT = "My broadband drops every evening around 8 PM and I already restarted the router twice."
ANALYSIS = {
    "intent": "restore broadband", "category": "broadband_connectivity",
    "product": "broadband", "severity": "HIGH", "sentiment": "FRUSTRATED",
    "confidence": 0.83, "needs_review": False,
    "rationale": "Recurring evening drops interrupt service.",
}


class FakeEncoder:
    dimension = 4

    def encode(self, texts):
        vectors = []
        for text in texts:
            lower = text.lower()
            if "phase7unique" in lower:
                vectors.append([0.0, 0.0, 0.0, 1.0])
            elif "broadband_connectivity" in lower or "drops" in lower:
                vectors.append([1.0, 0.0, 0.0, 0.0])
            else:
                digest = hashlib.sha256(text.encode()).digest()
                vectors.append([float(n + 1) for n in digest[:4]])
        return np.asarray(vectors, dtype=np.float32)


class EvidenceFake(FakeLLMClient):
    def __init__(self):
        super().__init__(ANALYSIS)

    def generate_resolution(self, _instruction, context):
        import json
        evidence = json.loads(context)["retrieved_evidence"]
        source_id = evidence[0]["source_id"]
        return {
            "problem_summary": "The broadband connection drops each evening.",
            "resolution_steps": [{
                "step_number": 1, "action": "Check the approved connection guidance.",
                "source_ids": [source_id],
            }],
            "escalation_recommendation": "Escalate if the dropouts continue.",
            "confidence_or_evidence_note": "Based on retrieved approved evidence.",
            "sources_used": [source_id], "insufficient_evidence": False,
        }


@pytest.fixture
def api(tmp_path):
    repository = Repository(URL.create("sqlite", database=str(tmp_path / "api.db")))
    seed_database(repository)
    search = SemanticSearch(repository, encoder=FakeEncoder(), index_dir=tmp_path / "indexes")
    provider = EvidenceFake()
    service = ApiServices(repository, search, provider, admin_key="test-admin-key")
    with TestClient(create_app(lambda: service)) as client:
        yield client, service, provider


def test_health_and_ready(api):
    client, service, _ = api
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert all(ready.json()[key] for key in ("database", "search_index", "embedding_model", "gemini_configured"))
    assert service.search.ticket_index is not None


def test_ready_unavailable(tmp_path):
    with TestClient(create_app(lambda: (_ for _ in ()).throw(RuntimeError("private database URL")))) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["database"] is False
        assert "private database URL" not in response.text


def test_analyze_valid_unknown_and_validation(api):
    client, _, provider = api
    response = client.post("/analyze", json={"complaint": COMPLAINT})
    assert response.status_code == 200
    assert response.json()["analysis"]["severity"] == "HIGH"
    assert response.json()["latency_ms"] >= 0
    provider.result = {**ANALYSIS, "category": "optical_signal_fault"}
    unknown = client.post("/analyze", json={"complaint": COMPLAINT}).json()["analysis"]
    assert unknown["category"] == "other"
    assert unknown["suggested_category"] == "optical_signal_fault"
    assert unknown["needs_review"] is True
    for complaint in ("", "   ", "x" * 3001):
        bad = client.post("/analyze", json={"complaint": complaint})
        assert bad.status_code == 422
        assert complaint not in bad.text if complaint else True


def test_complaint_limit_applies_to_every_api_route(api):
    client, _, _ = api
    for route in ("/analyze", "/search", "/resolve"):
        assert client.post(route, json={"complaint": "a" * 3000}).status_code == 200
        rejected = client.post(route, json={"complaint": "a" * 3001})
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "validation_error"
        assert "a" * 3001 not in rejected.text


@pytest.mark.parametrize("complaint", [
    "x", "afehtdgsdxzvsawe", "asdfghjkl", "😂", "123456789", "!!!@@@###",
    "I went to a movie today.", "I played a game today.",
    "hello hello hello", "phone laptop tablet mobile", "aaaaaa",
    "https://example.com/fragment",
])
def test_non_actionable_input_skips_search_and_rag(api, complaint):
    client, service, provider = api
    provider.result = {**ANALYSIS, "category": "other", "product": "other",
                       "confidence": 0.2, "needs_review": True}
    service.search.search = lambda *_args, **_kwargs: pytest.fail("search must be skipped")
    provider.generate_resolution = lambda *_args: pytest.fail("RAG must be skipped")
    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]
    assert body["non_actionable"] is True
    assert body["tickets"] == body["kb_articles"] == []
    assert body["source_ids"] == body["resolution"]["sources_used"] == []
    assert body["resolution"]["resolution_steps"] == []
    assert body["insufficient_evidence"] is True
    assert "No clear telecom issue" in body["resolution"]["problem_summary"]
    assert "Retrieval was skipped" in body["resolution"]["confidence_or_evidence_note"]
    assert "escalat" not in body["resolution"]["escalation_recommendation"].lower()


@pytest.mark.parametrize("complaint", [
    "My keyboard is not working", "My phone camera is broken",
    "My phone battery is not charging", "My laptop screen is cracked",
    "My speaker is damaged", "My mouse is not working",
    "My phone screen is flickering", "My laptop fan is making noise",
    "My camera app is crashing", "My phone storage is full",
])
def test_out_of_scope_device_issue_skips_retrieval_and_rag(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "intent": "repair a device hardware or software issue",
        "category": "other", "product": "other", "needs_review": True,
        "rationale": "This device issue is unrelated to telecom service.",
    }
    service.search.load_or_build = lambda: pytest.fail("FAISS must be skipped")
    service.search.search = lambda *_args, **_kwargs: pytest.fail("retrieval must be skipped")
    provider.generate_resolution = lambda *_args: pytest.fail("RAG must be skipped")

    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"] and body["non_actionable"] is True
    assert body["tickets"] == body["kb_articles"] == []
    assert body["source_ids"] == body["resolution"]["sources_used"] == []
    assert body["resolution"]["resolution_steps"] == []
    assert body["insufficient_evidence"] is True
    assert "telecom service problem" in body["resolution"]["escalation_recommendation"]
    assert "escalat" not in body["resolution"]["escalation_recommendation"].lower()


@pytest.mark.parametrize("complaint", [
    "My phone camera is broken", "My phone battery is not charging",
])
def test_explicit_non_telecom_analysis_overrides_known_phone_product(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "intent": "repair device hardware", "category": "other",
        "product": "mobile_prepaid", "needs_review": True,
        "rationale": "The issue is outside telecom support.",
        "suggested_category": "device_repair",
    }
    service.search.load_or_build = lambda: pytest.fail("FAISS must be skipped")
    provider.generate_resolution = lambda *_args: pytest.fail("RAG must be skipped")
    body = client.post("/resolve", json={"complaint": complaint}).json()
    assert body["non_actionable"] is True
    assert body["tickets"] == body["kb_articles"] == body["source_ids"] == []


def test_unknown_phone_hardware_fault_skips_without_exact_device_noun(api):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "intent": "repair hardware", "category": "other",
        "product": "other", "needs_review": True,
        "rationale": "A physical hardware fault is described.",
    }
    service.search.load_or_build = lambda: pytest.fail("FAISS must be skipped")
    provider.generate_resolution = lambda *_args: pytest.fail("RAG must be skipped")
    body = client.post("/resolve", json={"complaint": "My phone camera is broken"}).json()
    assert body["non_actionable"] is True
    assert body["tickets"] == body["kb_articles"] == body["source_ids"] == []


@pytest.mark.parametrize("complaint", [
    "My phone speaker is not working.",
    "My phone speaker is broken.",
    "My phone speaker is damaged.",
])
def test_speaker_hardware_analysis_skips_search_and_rag_even_with_known_product(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "other", "product": "mobile_postpaid",
        "needs_review": True,
        "intent": "Repair or replace a malfunctioning phone speaker",
        "rationale": "Hardware issue with the device speaker is not covered by standard telecom network categories.",
    }
    service.search.load_or_build = lambda: pytest.fail("FAISS must be skipped")
    service.search.search = lambda *_args, **_kwargs: pytest.fail("retrieval must be skipped")
    provider.generate_resolution = lambda *_args: pytest.fail("RAG must be skipped")

    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"] and body["non_actionable"] is True
    assert body["tickets"] == body["kb_articles"] == body["source_ids"] == []
    assert body["resolution"]["resolution_steps"] == body["resolution"]["sources_used"] == []
    assert body["insufficient_evidence"] is True
    assert "telecom service problem" in body["resolution"]["escalation_recommendation"]
    assert "escalat" not in body["resolution"]["escalation_recommendation"].lower()


@pytest.mark.parametrize("complaint", [
    "I cannot hear the other person during calls.",
    "Call audio keeps cutting out.",
    "My calls have no sound.",
    "My phone speaker is broken and my mobile data is down.",
])
def test_call_audio_and_mixed_service_issues_still_retrieve_with_hardware_analysis(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "other", "product": "mobile_postpaid",
        "needs_review": True,
        "intent": "Check possible device hardware fault",
        "rationale": "A hardware issue may be involved.",
    }
    calls = []
    original = service.search.search

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    service.search.search = counted
    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    assert response.json()["non_actionable"] is False
    assert calls == [1]


@pytest.mark.parametrize("complaint", [
    "My camera is not working and I also cannot send SMS messages.",
    "My camera is broken and I cannot send SMS messages",
    "My battery is draining and my mobile data is slow",
    "My screen is cracked and I cannot receive calls",
    "My speaker is damaged and my SIM has no signal",
    "My battery drains quickly and my mobile internet is extremely slow.",
    "My camera is not working and I also cannot send text messages.",
])
def test_mixed_hardware_and_telecom_service_problem_still_retrieves(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "other", "product": "mobile_postpaid",
        "needs_review": True,
        "intent": "Repair device hardware and restore messaging or telecom service",
        "rationale": "A hardware issue and telecom service problem are both reported.",
    }
    calls = []
    original = service.search.search

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    service.search.search = counted
    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    assert response.json()["non_actionable"] is False
    assert calls == [1]


@pytest.mark.parametrize("complaint", [
    "I forgot my laptop password",
    "I forgot my Windows password",
    "I cannot log into my laptop",
    "My computer login password is not working",
])
def test_local_device_password_issue_skips_telecom_account_guidance(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "account_access", "product": "account_services",
        "intent": "Reset an account password",
        "rationale": "The customer cannot access an account.",
    }
    service.search.load_or_build = lambda: pytest.fail("FAISS must be skipped")
    service.search.search = lambda *_args, **_kwargs: pytest.fail("retrieval must be skipped")
    provider.generate_resolution = lambda *_args: pytest.fail("RAG must be skipped")
    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    body = response.json()
    assert body["non_actionable"] is True
    assert body["tickets"] == body["kb_articles"] == body["source_ids"] == []
    assert body["resolution"]["resolution_steps"] == body["resolution"]["sources_used"] == []
    assert body["insufficient_evidence"] is True
    assert "telecom service problem" in body["resolution"]["escalation_recommendation"]


@pytest.mark.parametrize("complaint", [
    "I forgot my telecom account password",
    "I cannot log into my mobile provider account",
    "My customer portal password is not working",
    "My telecom account is locked",
    "I forgot my laptop password for the customer portal",
])
def test_telecom_account_access_still_retrieves(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "account_access", "product": "account_services",
        "intent": "Restore telecom account access",
        "rationale": "Account credentials need assistance.",
    }
    calls = []
    original = service.search.search

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    service.search.search = counted
    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    assert response.json()["non_actionable"] is False
    assert calls == [1]


@pytest.mark.parametrize("complaint", [
    "My mobile data is not working", "My phone has no network signal",
    "My phone has no mobile network",
    "Calls keep dropping", "My SIM is not activating",
    "My broadband is slow", "My recharge is missing",
    "Roaming is not working", "My phone camera is broken and mobile data is down",
])
def test_real_telecom_service_problem_proceeds_despite_device_wording(api, complaint):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "other", "product": "other", "needs_review": True,
        "intent": "check a device issue", "rationale": "A device problem may be involved.",
    }
    calls = []
    original = service.search.search

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    service.search.search = counted
    body = client.post("/resolve", json={"complaint": complaint}).json()
    assert body["non_actionable"] is False
    assert calls == [1]


def test_billing_issue_proceeds_without_device_words(api):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "billing_dispute", "product": "mobile_postpaid",
        "intent": "correct a duplicate charge", "rationale": "Customer reports double billing.",
    }
    body = client.post("/resolve", json={"complaint": "I was charged twice"}).json()
    assert body["non_actionable"] is False
    assert body["tickets"] and body["kb_articles"]


def test_vague_mobile_device_wording_is_not_enough_to_block(api):
    client, service, provider = api
    provider.result = {
        **ANALYSIS, "category": "other", "product": "other", "needs_review": True,
        "intent": "check a mobile device", "rationale": "Symptoms are vague; a device issue is possible.",
    }
    calls = []
    original = service.search.search

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    service.search.search = counted
    body = client.post("/resolve", json={"complaint": "My mobile is not working properly."}).json()
    assert body["non_actionable"] is False
    assert calls == [1]


@pytest.mark.parametrize("complaint", [
    "My mobile is not working properly.", "Internet is slow sometimes.",
    "There is some issue with my SIM.", "My broadband has a problem.",
    "Calls are not working well.", "My phone network is bad.",
])
def test_vague_telecom_input_still_searches(api, complaint):
    client, service, provider = api
    calls = []
    original = service.search.search

    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    service.search.search = counted
    provider.result = {**ANALYSIS, "category": "other", "product": "other",
                       "confidence": 0.45, "needs_review": True}
    response = client.post("/resolve", json={"complaint": complaint})
    assert response.status_code == 200
    assert response.json()["non_actionable"] is False
    assert len(calls) == 1
    assert response.json()["tickets"] and response.json()["kb_articles"]


@pytest.mark.parametrize("analysis_changes", [
    {"needs_review": True}, {"confidence": 0.55},
])
def test_review_or_moderate_confidence_alone_does_not_block_retrieval(api, analysis_changes):
    client, service, provider = api
    provider.result = {**ANALYSIS, **analysis_changes}
    response = client.post("/resolve", json={"complaint": COMPLAINT})
    assert response.status_code == 200
    assert response.json()["non_actionable"] is False
    assert response.json()["tickets"] and response.json()["kb_articles"]


def test_unfamiliar_wording_recognized_by_analysis_is_not_blocked(api):
    client, _, provider = api
    provider.result = {**ANALYSIS, "category": "mobile_network", "product": "mobile_prepaid"}
    response = client.post("/resolve", json={"complaint": "My texts never arrive."})
    assert response.status_code == 200
    assert response.json()["non_actionable"] is False
    assert response.json()["tickets"] and response.json()["kb_articles"]


def test_provider_failure_and_missing_configuration(api):
    client, service, provider = api
    provider.result = GeminiProviderError("secret-provider-detail")
    failed = client.post("/analyze", json={"complaint": COMPLAINT})
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "provider_error"
    assert "secret-provider-detail" not in failed.text
    service.client = None
    missing = client.post("/analyze", json={"complaint": COMPLAINT})
    assert missing.status_code == 503
    assert missing.json()["error"]["code"] == "missing_configuration"


def test_search_validation_and_evidence_filter(api):
    client, _, _ = api
    response = client.post("/search", json={
        "complaint": COMPLAINT, "top_k_tickets": 20, "top_k_kb": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["tickets"] and body["kb_articles"]
    assert all("similarity_score" in match for match in body["tickets"] + body["kb_articles"])
    assert not {"T-009", "T-010", "KB-020", "KB-024"} & {
        match["source_id"] for match in body["tickets"] + body["kb_articles"]
    }
    assert body["latency_ms"] >= 0
    for invalid in (0, -1, 21, True, "3"):
        bad = client.post("/search", json={"complaint": COMPLAINT, "top_k_tickets": invalid})
        assert bad.status_code == 422


def test_search_failure_is_sanitized(api):
    client, service, _ = api
    service.search.search = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("private model path"))
    response = client.post("/search", json={"complaint": COMPLAINT})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "search_unavailable"
    assert "private model path" not in response.text


def test_resolve_end_to_end_and_weak_evidence(api):
    client, service, _ = api
    response = client.post("/resolve", json={"complaint": COMPLAINT})
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["product"] == "broadband"
    assert body["tickets"] and body["kb_articles"]
    assert body["resolution"]["resolution_steps"][0]["source_ids"] == body["source_ids"]
    assert body["insufficient_evidence"] is False
    assert body["latency_ms"] >= 0

    service.search.search = lambda *_args, **_kwargs: SearchResults([], [])
    weak = client.post("/resolve", json={"complaint": COMPLAINT})
    assert weak.status_code == 200
    assert weak.json()["insufficient_evidence"] is True
    assert weak.json()["source_ids"] == []


def test_resolve_rejects_hallucinated_citation_and_provider_failure(api):
    client, _, provider = api
    provider.generate_resolution = lambda *_args: {
        "problem_summary": "Dropouts", "resolution_steps": [{
            "step_number": 1, "action": "Follow an invented ticket.", "source_ids": ["T-999"],
        }], "escalation_recommendation": "Escalate", "confidence_or_evidence_note": "Evidence",
        "sources_used": ["T-999"], "insufficient_evidence": False,
    }
    rejected = client.post("/resolve", json={"complaint": COMPLAINT})
    assert rejected.status_code == 502
    assert rejected.json()["error"]["code"] == "grounding_error"
    provider.generate_resolution = lambda *_args: (_ for _ in ()).throw(GeminiProviderError("secret"))
    failed = client.post("/resolve", json={"complaint": COMPLAINT})
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "provider_error"
    assert "secret" not in failed.text


def test_admin_authorization_validation_and_searchable_update(api):
    client, service, _ = api
    ticket = service.repository.get_ticket("T-001").model_dump(mode="json")
    ticket.update(ticket_id="T-121", complaint="phase7unique optical service fault",
                  created_at=datetime.now(timezone.utc).isoformat(),
                  updated_at=datetime.now(timezone.utc).isoformat())
    assert client.post("/admin/tickets", json=ticket).status_code == 401
    assert client.post("/admin/tickets", json=ticket, headers={"X-Admin-Key": "wrong"}).status_code == 401
    headers = {"X-Admin-Key": "test-admin-key"}
    malformed = client.post("/admin/tickets", json={**ticket, "approved": "yes"}, headers=headers)
    assert malformed.status_code == 422
    assert client.post("/admin/taxonomy", json={"kind": "category", "value": "Bad Value", "reviewed_by": "x"}, headers=headers).status_code == 422
    added = client.post("/admin/tickets", json=ticket, headers=headers)
    assert added.status_code == 200
    assert added.json() == {"change": "inserted", "index_refreshed": True}
    found = client.post("/search", json={"complaint": "phase7unique"}).json()
    assert found["tickets"][0]["source_id"] == "T-121"
    article = service.repository.get_kb_article("KB-001").model_dump(mode="json")
    article.update(kb_id="KB-025", title="phase7unique guidance",
                   created_at=datetime.now(timezone.utc).isoformat(),
                   updated_at=datetime.now(timezone.utc).isoformat())
    assert client.post("/admin/kb", json=article, headers=headers).status_code == 200
    taxonomy = client.post("/admin/taxonomy", json={
        "kind": "category", "value": "optical_signal_fault", "reviewed_by": "test-reviewer",
    }, headers=headers)
    assert taxonomy.status_code == 200
    assert "optical_signal_fault" in service.repository.list_taxonomy("category")
    duplicate = client.post("/admin/taxonomy", json={
        "kind": "category", "value": "optical_signal_fault", "reviewed_by": "test-reviewer",
    }, headers=headers)
    assert duplicate.status_code == 409


def test_admin_revocation_disappears_from_api_evidence(api):
    client, service, _ = api
    before = client.post("/search", json={"complaint": COMPLAINT, "top_k_tickets": 20}).json()
    assert "T-001" in {item["source_id"] for item in before["tickets"]}
    ticket = service.repository.get_ticket("T-001").model_dump(mode="json")
    ticket["approved"] = False
    ticket["updated_at"] = datetime.now(timezone.utc).isoformat()
    changed = client.post("/admin/tickets", json=ticket, headers={"X-Admin-Key": "test-admin-key"})
    assert changed.status_code == 200
    after = client.post("/search", json={"complaint": COMPLAINT, "top_k_tickets": 20}).json()
    assert "T-001" not in {item["source_id"] for item in after["tickets"]}


def test_admin_disabled_and_private_logging(api, caplog):
    client, service, _ = api
    service.admin_key = None
    response = client.post("/admin/taxonomy", json={
        "kind": "category", "value": "another_class", "reviewed_by": "reviewer",
    }, headers={"X-Admin-Key": "private-admin-secret"})
    assert response.status_code == 503
    with caplog.at_level("INFO", logger="app.api"):
        client.post("/analyze", json={"complaint": "private-customer-complaint"})
    assert "private-customer-complaint" not in caplog.text
    assert "private-admin-secret" not in caplog.text


def test_cors_is_restrictive(api):
    client, _, _ = api
    allowed = client.options("/analyze", headers={
        "Origin": "http://localhost:8501", "Access-Control-Request-Method": "POST",
    })
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8501"
    blocked = client.options("/analyze", headers={
        "Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST",
    })
    assert blocked.status_code == 400
