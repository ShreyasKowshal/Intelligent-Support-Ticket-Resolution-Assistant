"""Run a local semantic-search example from the command line."""

import argparse

from app.search import SemanticSearch
from app.storage import Repository

EXAMPLE = "My internet keeps dropping every evening and I already restarted the router."


def main() -> None:
    parser = argparse.ArgumentParser(description="Search approved telecom support evidence")
    parser.add_argument("--query", default=EXAMPLE, help="Natural-language complaint")
    parser.add_argument("--tickets", type=int, default=None, help="Number of ticket matches")
    parser.add_argument("--kb", type=int, default=None, help="Number of KB matches")
    args = parser.parse_args()
    repository = Repository()
    try:
        repository.initialize()
        search = SemanticSearch(repository)
        try:
            mode = search.load_or_build()
            results = search.search(args.query, ticket_k=args.tickets, kb_k=args.kb)
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(f"Search failed: {exc}") from exc
        print(f"Index: {mode}. Similarity scores are not confidence probabilities.")
        print(f"Query: {args.query}\nTop tickets:")
        for match in results.tickets:
            print(f"  {match.source_id} score={match.similarity_score:.3f} [{match.category}] {match.complaint}")
            print(f"    Resolution: {match.resolution}")
        print("Top KB articles:")
        for match in results.kb_articles:
            print(f"  {match.source_id} score={match.similarity_score:.3f} [{match.category}] {match.title}")
            print(f"    {match.content}")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
