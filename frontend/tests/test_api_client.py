"""Frontend HTTP tests use MockTransport and never call Gemini."""

import json

import httpx
import pytest

from frontend.api_client import (
    BackendConnectionError, FrontendError, check_backend_readiness,
    get_api_base_url, resolve_complaint,
)

COMPLAINT = "My broadband drops every evening around 8 PM."


def response_body():
    return {
        "analysis": {
            "intent": "restore broadband", "category": "broadband_connectivity",
            "product": "broadband", "severity": "HIGH", "sentiment": "FRUSTRATED",
            "confidence": 0.8, "needs_review": False,
            "rationale": "Repeated failures", "suggested_category": None,
        },
        "tickets": [{
            "source_id": "T-001", "complaint": "Broadband fails", "product": "broadband",
            "category": "broadband_connectivity", "resolution": "Check the line.",
            "similarity_score": 0.78,
        }],
        "kb_articles": [{
            "source_id": "KB-001", "title": "Connection checks",
            "content": "Use the approved line checks.", "category": "broadband_connectivity",
            "similarity_score": 0.71,
        }],
        "resolution": {
            "problem_summary": "Recurring drops", "resolution_steps": [{
                "step_number": 1, "action": "Check the line status.",
                "source_ids": ["KB-001"],
            }],
            "escalation_recommendation": "Escalate if persistent.",
            "confidence_or_evidence_note": "Based on approved guidance.",
            "sources_used": ["KB-001"], "insufficient_evidence": False,
        },
        "source_ids": ["KB-001"], "insufficient_evidence": False,
        "latency_ms": 123.4,
    }


def transport_for(status, body):
    return httpx.MockTransport(lambda _request: httpx.Response(status, json=body))


def ready_body(**changes):
    return {
        "status": "ready", "database": True, "search_index": True,
        "embedding_model": True, "gemini_configured": True, **changes,
    }


def test_readiness_uses_only_ready_and_requires_all_dependencies(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8765/")
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        return httpx.Response(200, json=ready_body())

    assert check_backend_readiness(transport=httpx.MockTransport(handler)) == "ready"
    assert calls == [("GET", "http://localhost:8765/ready")]
    assert check_backend_readiness(transport=transport_for(
        200, ready_body(search_index=False)
    )) == "unavailable"


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("private"), httpx.ConnectError("private")])
def test_readiness_connection_failures_mean_starting(failure):
    transport = httpx.MockTransport(lambda _request: (_ for _ in ()).throw(failure))
    assert check_backend_readiness(transport=transport) == "starting"


def test_readiness_distinguishes_startup_from_persistent_failure():
    assert check_backend_readiness(transport=transport_for(
        503, ready_body(status="not_ready", search_index=False)
    )) == "starting"
    assert check_backend_readiness(transport=transport_for(
        503, ready_body(status="not_ready", gemini_configured=False)
    )) == "unavailable"
    assert check_backend_readiness(transport=transport_for(404, {})) == "unavailable"


def test_resolve_calls_only_backend_route_and_parses_response(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8765/")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response_body())

    result = resolve_complaint(COMPLAINT, transport=httpx.MockTransport(handler))
    assert len(calls) == 1
    assert str(calls[0].url) == "http://localhost:8765/resolve"
    assert json.loads(calls[0].content) == {"complaint": COMPLAINT}
    assert result.analysis.category == "broadband_connectivity"
    assert result.tickets[0].source_id == "T-001"
    assert result.kb_articles[0].source_id == "KB-001"
    assert result.resolution.resolution_steps[0].source_ids == ["KB-001"]
    assert result.latency_ms == 123.4


def test_unknown_and_insufficient_evidence_responses_parse():
    body = response_body()
    body["analysis"].update(category="other", needs_review=True, suggested_category="optical_signal_fault")
    body["tickets"] = []
    body["kb_articles"] = []
    body["resolution"].update(resolution_steps=[], sources_used=[], insufficient_evidence=True)
    body["source_ids"] = []
    body["insufficient_evidence"] = True
    result = resolve_complaint(COMPLAINT, transport=transport_for(200, body))
    assert result.analysis.needs_review is True
    assert result.analysis.suggested_category == "optical_signal_fault"
    assert result.insufficient_evidence is True


@pytest.mark.parametrize("invalid", ["", "   ", "x" * 4001])
def test_local_complaint_validation_prevents_http(invalid):
    def fail(_request):
        raise AssertionError("HTTP should not be called")

    with pytest.raises(FrontendError):
        resolve_complaint(invalid, transport=httpx.MockTransport(fail))


@pytest.mark.parametrize("code,expected", [
    ("provider_error", "AI provider"),
    ("provider_timeout", "timed out"),
    ("grounding_error", "citation"),
    ("missing_configuration", "not configured"),
])
def test_sanitized_api_errors(code, expected):
    transport = transport_for(502, {"error": {"code": code, "message": "private provider details"}})
    with pytest.raises(FrontendError) as error:
        resolve_complaint(COMPLAINT, transport=transport)
    assert expected in str(error.value)
    assert "private provider details" not in str(error.value)


def test_timeout_and_connection_error_are_concise():
    for failure, expected in (
        (httpx.ReadTimeout("private timeout details"), "timed out"),
        (httpx.ConnectError("private address"), "Backend is starting"),
    ):
        transport = httpx.MockTransport(lambda _request: (_ for _ in ()).throw(failure))
        with pytest.raises(FrontendError) as error:
            resolve_complaint(COMPLAINT, transport=transport)
        assert expected in str(error.value)
        assert "private" not in str(error.value)


def test_connection_error_has_distinct_type_for_readiness_retry():
    transport = httpx.MockTransport(lambda _request: (_ for _ in ()).throw(httpx.ConnectError("private")))
    with pytest.raises(BackendConnectionError):
        resolve_complaint(COMPLAINT, transport=transport)


def test_unexpected_server_error_is_actionable_and_sanitized():
    with pytest.raises(FrontendError, match="unexpected error") as error:
        resolve_complaint(COMPLAINT, transport=transport_for(500, {"detail": "private failure"}))
    assert "private failure" not in str(error.value)


@pytest.mark.parametrize("body", [{}, {"analysis": {}}, [1, 2, 3]])
def test_invalid_success_response_is_rejected(body):
    with pytest.raises(FrontendError, match="invalid response"):
        resolve_complaint(COMPLAINT, transport=transport_for(200, body))


def test_inconsistent_citation_status_is_rejected():
    body = response_body()
    body["source_ids"] = ["T-999"]
    with pytest.raises(FrontendError, match="invalid response"):
        resolve_complaint(COMPLAINT, transport=transport_for(200, body))


def test_uncatalogued_step_citation_is_rejected():
    body = response_body()
    body["resolution"]["resolution_steps"][0]["source_ids"] = ["T-999"]
    with pytest.raises(FrontendError, match="invalid response"):
        resolve_complaint(COMPLAINT, transport=transport_for(200, body))


def test_invalid_backend_url_is_not_echoed(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://private:secret@example.test")
    with pytest.raises(FrontendError) as error:
        get_api_base_url()
    assert "secret" not in str(error.value)
