"""Measure warm FastAPI route latency with a fake provider and real local search."""

import json

from fastapi.testclient import TestClient

from app.api_service import ApiServices
from app.main import create_app
from app.search import SemanticSearch
from app.storage import Repository
from evaluation.metrics import latency_metrics
from evaluation.evaluate_rag import resolution_with

DEFAULT_RUNS = 7
SAMPLE_COMPLAINT = (
    "My broadband drops every evening around 8 PM and I already restarted the router twice."
)


class LatencyFakeProvider:
    def generate_analysis(self, _instruction: str, _complaint: str) -> dict:
        return {
            "intent": "restore_service", "category": "broadband_connectivity",
            "product": "broadband", "severity": "HIGH", "sentiment": "FRUSTRATED",
            "confidence": 0.8, "needs_review": False,
            "rationale": "Recurring drops interrupt service.",
        }

    def generate_resolution(self, _instruction: str, context: str) -> dict:
        source_id = json.loads(context)["retrieved_evidence"][0]["source_id"]
        return resolution_with("Review the approved connection guidance.", source_id)


def evaluate(repository: Repository, search: SemanticSearch, runs: int = DEFAULT_RUNS) -> dict:
    if runs < 2:
        raise ValueError("system latency needs multiple runs")
    service = ApiServices(repository, search, LatencyFakeProvider())
    app = create_app(lambda: service)
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        if health.status_code != 200 or ready.status_code != 200:
            raise RuntimeError("evaluation API failed health or readiness")
        latency = {}
        for path in ("/analyze", "/search", "/resolve"):
            payload = {"complaint": SAMPLE_COMPLAINT}
            warm = client.post(path, json=payload)
            warm.raise_for_status()
            samples = []
            for _ in range(runs):
                response = client.post(path, json=payload)
                response.raise_for_status()
                samples.append(response.json()["latency_ms"])
            latency[path] = latency_metrics(samples)
        return {
            "mode": "in_process_fastapi_fake_provider_warm",
            "latency_source": "API response latency_ms; excludes test-client transport and cold model/index load",
            "runs_per_route": runs,
            "routes": latency,
            "health": {"status_code": health.status_code, **health.json()},
            "ready": {"status_code": ready.status_code, **ready.json()},
            "readiness_limitation": "Configured fake provider and local dependencies; no Gemini network probe.",
        }
