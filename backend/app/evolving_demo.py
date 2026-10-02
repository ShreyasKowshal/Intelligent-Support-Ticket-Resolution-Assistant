"""Demonstrate a reviewed new class becoming searchable without retraining."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy.engine import URL

from app.analysis import ComplaintAnalyzer
from app.ingestion import IngestionService
from app.llm import FakeLLMClient
from app.models import SupportTicket, TaxonomyValue
from app.search import SemanticSearch
from app.seed import seed_database
from app.storage import Repository


def main() -> None:
    complaint = "My fiber modem has an optical signal red alarm and no connection."
    with TemporaryDirectory() as directory:
        root = Path(directory)
        url = URL.create("sqlite", database=str(root / "support.db"))
        repository = Repository(url)
        try:
            seed_database(repository)
            search = SemanticSearch(repository, index_dir=root / "indexes")
            search.load_or_build()
            fake = FakeLLMClient({
                "intent": "restore optical service", "category": "optical_signal_fault",
                "product": "broadband", "severity": "HIGH", "sentiment": "FRUSTRATED",
                "confidence": 0.82, "needs_review": False,
                "rationale": "An optical alarm accompanies loss of connection.",
            })
            analyzer = ComplaintAnalyzer.from_repository(fake, repository)
            before = analyzer.analyze(complaint)
            prior = search.search(complaint)
            print(f"Before: category={before.category}, needs_review={before.needs_review}")
            print("Before top ticket:",
                  f"{prior.tickets[0].source_id} ({prior.tickets[0].similarity_score:.3f})"
                  if prior.tickets else "none")

            service = IngestionService(repository, search)
            service.add_reviewed_taxonomy_value(
                TaxonomyValue(kind="category", value="optical_signal_fault"), "demo_admin"
            )
            now = datetime.now(timezone.utc)
            outcome = service.upsert_ticket(SupportTicket(
                ticket_id="T-121", complaint=complaint, product="broadband",
                category="optical_signal_fault", severity="HIGH", sentiment="FRUSTRATED",
                resolution="Check the approved optical signal guidance and escalate if the alarm persists.",
                status="resolved", approved=True, created_at=now, updated_at=now,
            ))
            after = analyzer.analyze(complaint)
            result = search.search(complaint)
            print(f"After: category={after.category}, needs_review={after.needs_review}")
            print(f"Update: {outcome.change}, index_refreshed={outcome.index_refreshed}")
            print("After top ticket:",
                  f"{result.tickets[0].source_id} ({result.tickets[0].similarity_score:.3f})"
                  if result.tickets else "none")
            print("Reviewed category stored:", "optical_signal_fault" in repository.list_taxonomy("category"))
            print("Model retraining: none")
        finally:
            repository.close()

        restarted_repository = Repository(url)
        try:
            restarted_search = SemanticSearch(restarted_repository, index_dir=root / "indexes")
            mode = restarted_search.load_or_build()
            restarted = restarted_search.search(complaint)
            print(f"Restart: index={mode}, top_ticket={restarted.tickets[0].source_id}")
            assert restarted.tickets[0].source_id == "T-121"
        finally:
            restarted_repository.close()


if __name__ == "__main__":
    main()
