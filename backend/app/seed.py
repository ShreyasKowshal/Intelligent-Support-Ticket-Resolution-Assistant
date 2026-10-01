"""Validate and load the synthetic, repeatable seed corpus."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import Field, ValidationError, field_validator

from app.models import (
    KnowledgeBaseArticle,
    Record,
    Severity,
    SupportTicket,
    TaxonomyValue,
)
from app.storage import Repository, StorageUnavailableError

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"
SENTIMENTS = (
    "negative", "frustrated", "neutral", "negative", "frustrated",
    "negative", "positive", "negative", "frustrated", "negative",
)


class TicketCase(Record):
    product: str = Field(min_length=1)
    category: str = Field(min_length=1)
    severity: Severity
    resolution: str = Field(min_length=1)
    complaints: list[str] = Field(min_length=10, max_length=10)

    @field_validator("product", "category", "resolution")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be blank")
        return value

    @field_validator("complaints")
    @classmethod
    def nonblank_complaints(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("complaints cannot contain blank text")
        return [value.strip() for value in values]


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path}: {exc}") from exc


def _unique_ids(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label} IDs in seed data")


def load_seed_records(
    seed_dir: Path = SEED_DIR,
) -> tuple[list[TaxonomyValue], list[SupportTicket], list[KnowledgeBaseArticle]]:
    """Parse every file before writing any database records."""
    try:
        raw_taxonomy = _read_json(seed_dir / "taxonomy.json")
        if not isinstance(raw_taxonomy, dict):
            raise ValueError("taxonomy.json must contain an object")
        required_kinds = {"product", "category", "severity", "sentiment"}
        if set(raw_taxonomy) != required_kinds:
            raise ValueError("taxonomy.json must contain product, category, severity, and sentiment lists")
        if any(not isinstance(values, list) or not values for values in raw_taxonomy.values()):
            raise ValueError("each taxonomy kind must contain a nonempty list")
        if set(raw_taxonomy["severity"]) != {"low", "medium", "high", "critical"}:
            raise ValueError("severity taxonomy must contain low, medium, high, and critical")
        if set(raw_taxonomy["sentiment"]) != {"positive", "neutral", "negative", "frustrated"}:
            raise ValueError("sentiment taxonomy must contain positive, neutral, negative, and frustrated")
        taxonomy = [
            TaxonomyValue(kind=kind, value=value)
            for kind, values in raw_taxonomy.items()
            for value in values
        ]
        _unique_ids([f"{item.kind}/{item.value}" for item in taxonomy], "taxonomy")

        raw_cases = _read_json(seed_dir / "ticket_cases.json")
        if not isinstance(raw_cases, list):
            raise ValueError("ticket_cases.json must contain a list")
        cases = [TicketCase.model_validate(item) for item in raw_cases]
        ticket_records: list[SupportTicket] = []
        for case_number, case in enumerate(cases):
            for variant, complaint in enumerate(case.complaints):
                number = case_number * 10 + variant + 1
                created_at = datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(days=number - 1)
                is_open = variant == 8
                ticket_records.append(
                    SupportTicket(
                        ticket_id=f"T-{number:03d}",
                        complaint=complaint,
                        product=case.product,
                        category=case.category,
                        severity=case.severity,
                        sentiment=SENTIMENTS[variant],
                        resolution="" if is_open else case.resolution,
                        status="open" if is_open else "resolved",
                        approved=variant < 8,
                        created_at=created_at,
                        updated_at=created_at if is_open else created_at + timedelta(days=1),
                    )
                )
        _unique_ids([ticket.ticket_id for ticket in ticket_records], "ticket")

        raw_articles = _read_json(seed_dir / "kb_articles.json")
        if not isinstance(raw_articles, list):
            raise ValueError("kb_articles.json must contain a list")
        articles = [KnowledgeBaseArticle.model_validate(item) for item in raw_articles]
        _unique_ids([article.kb_id for article in articles], "KB")
        return taxonomy, ticket_records, articles
    except (TypeError, ValidationError) as exc:
        raise ValueError(f"Malformed seed data in {seed_dir}: {exc}") from exc


def seed_database(repository: Repository, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    taxonomy, tickets, articles = load_seed_records(seed_dir)
    repository.initialize()
    return repository.seed(taxonomy, tickets, articles)


def main() -> None:
    try:
        repository = Repository()
    except StorageUnavailableError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        try:
            inserted = seed_database(repository)
            print(f"Inserted: {inserted}")
            print(f"Totals: tickets={len(repository.list_tickets())}, KB={len(repository.list_kb_articles())}")
        except (ValueError, StorageUnavailableError) as exc:
            raise SystemExit(str(exc)) from exc
    finally:
        repository.close()


if __name__ == "__main__":
    main()
