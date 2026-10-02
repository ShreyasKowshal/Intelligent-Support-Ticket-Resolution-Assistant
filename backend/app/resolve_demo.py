"""Analyze, retrieve, and draft a cited resolution from the command line."""

import argparse
import sys
from pathlib import Path

# Allow both `python -m backend.app.resolve_demo` from the root and
# `python -m app.resolve_demo` from backend without changing older modules.
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

from app.analysis import ComplaintAnalyzer
from app.gemini_client import GeminiClient, GeminiProviderError, GeminiRateLimitError, GeminiTimeoutError, MissingApiKeyError
from app.llm import FakeLLMClient
from app.rag import GroundingError, RAGGenerator
from app.search import SemanticSearch
from app.storage import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a cited telecom resolution")
    parser.add_argument("complaint", help="Raw customer complaint")
    parser.add_argument("--fake", action="store_true", help="Use fixed local LLM outputs without API calls")
    args = parser.parse_args()

    repository = Repository()
    client = None
    try:
        repository.initialize()
        if args.fake:
            client = FakeLLMClient({
                "intent": "restore broadband connection", "category": "broadband_connectivity",
                "product": "broadband", "severity": "HIGH", "sentiment": "FRUSTRATED",
                "confidence": 0.85, "needs_review": False,
                "rationale": "Repeated evening dropouts interrupt service.",
            })
        else:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
            client = GeminiClient()

        analysis = ComplaintAnalyzer.from_repository(client, repository).analyze(args.complaint)
        print("Complaint analysis:")
        print(analysis.model_dump_json(indent=2))

        search = SemanticSearch(repository)
        search.load_or_build()
        results = search.search(args.complaint)
        print("\nTop retrieved tickets:")
        for match in results.tickets:
            print(f"  {match.source_id} score={match.similarity_score:.3f} [{match.category}] {match.complaint}")
        print("Top KB articles:")
        for match in results.kb_articles:
            print(f"  {match.source_id} score={match.similarity_score:.3f} [{match.category}] {match.title}")

        if args.fake:
            ids = [item.source_id for item in results.kb_articles[:1] + results.tickets[:1]]
            client.resolution_result = {
                "problem_summary": "The customer reports recurring connection drops.",
                "resolution_steps": [{
                    "step_number": 1,
                    "action": "Check the approved connection guidance and confirm whether the issue persists.",
                    "source_ids": ids,
                }],
                "escalation_recommendation": "Escalate if the checks do not restore stable service.",
                "confidence_or_evidence_note": "Drafted from the retrieved approved evidence.",
                "sources_used": ids,
                "insufficient_evidence": False,
            }
        resolution = RAGGenerator(client).generate(
            args.complaint, analysis, results.tickets, results.kb_articles
        )
        print("\nCited resolution:")
        print(resolution.model_dump_json(indent=2))
    except (MissingApiKeyError, GeminiTimeoutError, GeminiRateLimitError, GeminiProviderError,
            GroundingError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    finally:
        if isinstance(client, GeminiClient):
            client.close()
        repository.close()


if __name__ == "__main__":
    main()
