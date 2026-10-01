"""Print a compact profile of the seeded local database."""

import pandas as pd

from app.storage import Repository, StorageUnavailableError


def print_profile(repository: Repository) -> None:
    ticket_rows = [ticket.model_dump(mode="json") for ticket in repository.list_tickets()]
    kb_rows = [article.model_dump(mode="json") for article in repository.list_kb_articles()]
    if not ticket_rows:
        raise ValueError("No tickets found. Run `python -m app.seed` first.")

    tickets = pd.DataFrame(ticket_rows)
    articles = pd.DataFrame(kb_rows)
    print(f"Total tickets: {len(tickets)}")
    print(f"Resolved: {(tickets['status'] == 'resolved').sum()}; open: {(tickets['status'] == 'open').sum()}")
    print(f"Approved: {tickets['approved'].sum()}; unapproved: {(~tickets['approved']).sum()}")
    print(f"Resolution evidence tickets: {len(repository.list_tickets(evidence_only=True))}")
    for column in ("category", "product", "severity", "sentiment"):
        print(f"Tickets by {column}:")
        print(tickets[column].value_counts().sort_index().to_string())
    print(f"KB articles: {len(articles)}; approved: {articles['approved'].sum()}")
    print("Missing/blank ticket fields:")
    missing = tickets.isna().sum() + tickets.map(lambda value: isinstance(value, str) and not value.strip()).sum()
    print(missing.to_string())
    print("Missing/blank KB fields:")
    kb_missing = articles.isna().sum() + articles.map(lambda value: isinstance(value, str) and not value.strip()).sum()
    print(kb_missing.to_string())


def main() -> None:
    try:
        repository = Repository()
    except StorageUnavailableError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        repository.initialize()
        print_profile(repository)
    except (ValueError, StorageUnavailableError) as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        repository.close()


if __name__ == "__main__":
    main()
