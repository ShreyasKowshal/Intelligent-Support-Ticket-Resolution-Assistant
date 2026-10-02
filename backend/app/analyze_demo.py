"""Run a single complaint analysis with Gemini or a deterministic fake."""

import argparse
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

from .analysis import ComplaintAnalyzer
from .gemini_client import GeminiClient, GeminiProviderError, GeminiRateLimitError, GeminiTimeoutError, MissingApiKeyError
from .llm import FakeLLMClient
from .seed import seed_database
from .storage import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one telecom complaint")
    parser.add_argument("complaint", help="Raw customer complaint")
    parser.add_argument("--fake", action="store_true", help="Use a fixed local result without an API call")
    args = parser.parse_args()

    client = None
    if args.fake:
        client = FakeLLMClient({
            "intent": "restore broadband connection", "category": "broadband_connectivity",
            "product": "broadband", "severity": "HIGH", "sentiment": "FRUSTRATED",
            "confidence": 0.85, "needs_review": False,
            "rationale": "Repeated evening dropouts interrupt service.",
            "suggested_category": None,
        })
    else:
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        try:
            client = GeminiClient()
        except MissingApiKeyError as exc:
            parser.exit(2, f"{exc}\n")
    try:
        repository = Repository()
        try:
            seed_database(repository)
            result = ComplaintAnalyzer.from_repository(client, repository).analyze(args.complaint)
            print(result.model_dump_json(indent=2))
        finally:
            repository.close()
    except (GeminiTimeoutError, GeminiRateLimitError, GeminiProviderError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    finally:
        if isinstance(client, GeminiClient):
            client.close()


if __name__ == "__main__":
    main()
