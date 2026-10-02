"""Run the API over local HTTP with a seeded database and fake LLM."""

import json
import socket
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import numpy as np
import uvicorn
from sqlalchemy.engine import URL

from app.api_service import ApiServices
from app.main import create_app
from app.search import SemanticSearch
from app.seed import seed_database
from app.storage import Repository


class DemoEncoder:
    dimension = 4

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray([[1.0, 0.0, 0.0, 0.0] for _ in texts], dtype=np.float32)


class DemoProvider:
    def generate_analysis(self, _instruction: str, _complaint: str) -> dict:
        return {
            "intent": "restore broadband service", "category": "broadband_connectivity",
            "product": "broadband", "severity": "HIGH", "sentiment": "FRUSTRATED",
            "confidence": 0.83, "needs_review": False,
            "rationale": "Recurring evening drops interrupt service.",
        }

    def generate_resolution(self, _instruction: str, context: str) -> dict:
        source_id = json.loads(context)["retrieved_evidence"][0]["source_id"]
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


def main() -> None:
    complaint = "My broadband drops every evening around 8 PM and I already restarted the router twice."
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = Repository(URL.create("sqlite", database=str(root / "api.db")))
        seed_database(repository)
        service = ApiServices(
            repository, SemanticSearch(repository, DemoEncoder(), root / "indexes"), DemoProvider()
        )
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
            if not server.started:
                raise RuntimeError("API smoke server did not start")
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=20) as client:
                for method, path, payload in (
                    ("GET", "/health", None),
                    ("GET", "/ready", None),
                    ("POST", "/analyze", {"complaint": complaint}),
                    ("POST", "/search", {"complaint": complaint}),
                    ("POST", "/resolve", {"complaint": complaint}),
                ):
                    response = client.request(method, path, json=payload)
                    response.raise_for_status()
                    body = response.json()
                    if path == "/resolve":
                        assert body["source_ids"] and not body["insufficient_evidence"]
                    print(f"{method} {path}: {response.status_code}")
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("API smoke server did not stop")


if __name__ == "__main__":
    main()
