"""Build local semantic-search indexes from eligible database records."""

from app.search import SemanticSearch
from app.storage import Repository


def main() -> None:
    repository = Repository()
    try:
        repository.initialize()
        if not repository.list_tickets(evidence_only=True) and not repository.list_kb_articles(evidence_only=True):
            raise SystemExit("No approved evidence found. Run `python -m app.seed` first.")
        search = SemanticSearch(repository)
        try:
            search.build_indexes()
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(f"Index build failed: {exc}") from exc
        print(f"Ticket index: {search.ticket_index.ntotal} vectors")
        print(f"KB index: {search.kb_index.ntotal} vectors")
        print(f"Saved indexes to {search.index_dir}")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
