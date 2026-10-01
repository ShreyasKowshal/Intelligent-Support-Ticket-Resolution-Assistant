"""Run a single complaint analysis with Gemini or a deterministic fake."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .analysis import ComplaintAnalyzer
from .gemini_client import GeminiClient, GeminiProviderError, GeminiRateLimitError, GeminiTimeoutError, MissingApiKeyError
from .llm import FakeLLMClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one telecom complaint")
    parser.add_argument("complaint", help="Raw customer complaint")
    parser.add_argument("--fake", action="store_true", help="Use a fixed local result without an API call")
    args = parser.parse_args()

    taxonomy_path = Path(__file__).resolve().parents[1] / "data" / "seed" / "taxonomy.json"
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
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
        result = ComplaintAnalyzer(client, taxonomy["product"], taxonomy["category"]).analyze(args.complaint)
        print(result.model_dump_json(indent=2))
    except (GeminiTimeoutError, GeminiRateLimitError, GeminiProviderError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    finally:
        if isinstance(client, GeminiClient):
            client.close()


if __name__ == "__main__":
    main()
