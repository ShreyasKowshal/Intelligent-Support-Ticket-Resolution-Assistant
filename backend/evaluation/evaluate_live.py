"""Optional, small Gemini sample. Never used by deterministic tests or metrics."""

from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from app.analysis import ComplaintAnalyzer
from app.gemini_client import GeminiClient
from app.rag import RAGGenerator
from app.search import SemanticSearch
from app.storage import Repository
from evaluation.fixtures import held_out_queries

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_IDS = ("Q-001", "Q-004", "Q-008")


def evaluate(repository: Repository, search: SemanticSearch) -> dict:
    load_dotenv(ROOT / ".env", override=False)
    try:
        provider = GeminiClient()
    except Exception as exc:
        return {"status": "unavailable", "failure_type": type(exc).__name__, "samples": []}
    samples = []
    queries = {item["query_id"]: item for item in held_out_queries()}
    try:
        analyzer = ComplaintAnalyzer.from_repository(provider, repository)
        generator = RAGGenerator(provider)
        for query_id in SAMPLE_IDS:
            query = queries[query_id]
            start = perf_counter()
            try:
                analysis = analyzer.analyze(query["complaint"])
                matches = search.search(query["complaint"])
                resolution = generator.generate(
                    query["complaint"], analysis, matches.tickets, matches.kb_articles,
                )
            except Exception as exc:
                return {
                    "status": "failed", "failure_type": type(exc).__name__,
                    "samples": samples, "failed_query_id": query_id,
                }
            samples.append({
                "query_id": query_id,
                "analysis": analysis.model_dump(mode="json"),
                "retrieved_ticket_ids": [item.source_id for item in matches.tickets],
                "retrieved_kb_ids": [item.source_id for item in matches.kb_articles],
                "resolution": resolution.model_dump(mode="json"),
                "latency_ms": round((perf_counter() - start) * 1000, 3),
            })
        return {
            "status": "pass", "mode": "live_gemini_observational_only",
            "samples": samples,
            "limitation": "Three synthetic cases; outputs require manual semantic review.",
        }
    finally:
        provider.close()
