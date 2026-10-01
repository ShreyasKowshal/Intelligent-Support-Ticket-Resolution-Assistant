"""Tests for the local dataset, validation, and repository rules."""

import json
import shutil

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.engine import URL

from app.models import SupportTicket, TaxonomyValue
from app.seed import SEED_DIR, load_seed_records, seed_database
from app.storage import (
    DuplicateRecordError,
    Repository,
    StorageUnavailableError,
    UnknownTaxonomyValueError,
)


@pytest.fixture
def repository(tmp_path):
    url = URL.create("sqlite", database=str(tmp_path / "test.db"))
    store = Repository(url)
    yield store
    store.close()


def test_storage_initialization_creates_small_schema(repository):
    repository.initialize()
    inspector = inspect(repository.engine)
    assert set(inspector.get_table_names()) == {
        "tickets", "kb_articles", "taxonomy_values", "embeddings"
    }
    assert {column["name"] for column in inspector.get_columns("embeddings")} == {
        "source_id", "source_type", "model_name", "model_version", "vector_bytes", "updated_at"
    }


def test_bad_database_url_has_clear_error():
    with pytest.raises(StorageUnavailableError, match="DATABASE_URL"):
        Repository("not-a-database-url")


def test_seed_loads_expected_records_and_is_idempotent(repository):
    assert seed_database(repository) == {"taxonomy": 24, "tickets": 120, "kb_articles": 24}
    assert seed_database(repository) == {"taxonomy": 0, "tickets": 0, "kb_articles": 0}
    assert len(repository.list_tickets()) == 120
    assert len(repository.list_kb_articles()) == 24


def test_retrieval_and_local_persistence(repository):
    seed_database(repository)
    ticket = repository.get_ticket("T-001")
    article = repository.get_kb_article("KB-001")
    assert ticket is not None and ticket.category == "broadband_connectivity"
    assert article is not None and article.title == "Intermittent broadband connection checks"
    assert repository.get_ticket("T-999") is None

    reopened = Repository(repository.engine.url)
    try:
        assert reopened.get_ticket("T-001") == ticket
    finally:
        reopened.close()


def test_only_resolved_approved_records_are_evidence(repository):
    seed_database(repository)
    evidence = {ticket.ticket_id for ticket in repository.list_tickets(evidence_only=True)}
    assert len(evidence) == 96
    assert "T-001" in evidence
    assert "T-009" not in evidence  # Open, with no resolution.
    assert "T-010" not in evidence  # Resolved, but unapproved.
    kb_evidence = {article.kb_id for article in repository.list_kb_articles(evidence_only=True)}
    assert len(kb_evidence) == 22
    assert "KB-020" not in kb_evidence
    assert "KB-024" not in kb_evidence


@pytest.mark.parametrize("field,value", [
    ("severity", "urgent"),
    ("sentiment", "angry-ish"),
    ("complaint", ""),
    ("resolution", ""),
])
def test_ticket_validation_rejects_invalid_values(field, value):
    _, tickets, _ = load_seed_records()
    data = tickets[0].model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        SupportTicket.model_validate(data)


def test_ticket_validation_rejects_missing_field():
    _, tickets, _ = load_seed_records()
    data = tickets[0].model_dump(mode="json")
    del data["product"]
    with pytest.raises(ValidationError):
        SupportTicket.model_validate(data)


def test_duplicate_ids_are_rejected(repository):
    seed_database(repository)
    ticket = repository.get_ticket("T-001")
    article = repository.get_kb_article("KB-001")
    assert ticket is not None and article is not None
    with pytest.raises(DuplicateRecordError):
        repository.add_ticket(ticket)
    with pytest.raises(DuplicateRecordError):
        repository.add_kb_article(article)
    with pytest.raises(DuplicateRecordError):
        repository.add_taxonomy_value(TaxonomyValue(kind="product", value="broadband"))


def test_taxonomy_controls_values(repository):
    seed_database(repository)
    assert repository.list_taxonomy("severity") == ["critical", "high", "low", "medium"]
    assert len(repository.list_taxonomy("category")) == 12
    ticket = repository.get_ticket("T-001")
    assert ticket is not None
    with pytest.raises(UnknownTaxonomyValueError):
        repository.add_ticket(ticket.model_copy(update={"ticket_id": "T-999", "product": "unknown"}))


def test_duplicate_seed_ids_fail_before_database_write(repository, tmp_path):
    seed_dir = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed_dir)
    path = seed_dir / "kb_articles.json"
    articles = json.loads(path.read_text(encoding="utf-8"))
    articles.append(articles[0])
    path.write_text(json.dumps(articles), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate KB IDs"):
        seed_database(repository, seed_dir)
    repository.initialize()
    assert repository.list_tickets() == []


def test_malformed_taxonomy_is_rejected(repository, tmp_path):
    seed_dir = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed_dir)
    path = seed_dir / "taxonomy.json"
    taxonomy = json.loads(path.read_text(encoding="utf-8"))
    taxonomy["product"] = "broadband"
    path.write_text(json.dumps(taxonomy), encoding="utf-8")
    with pytest.raises(ValueError, match="nonempty list"):
        seed_database(repository, seed_dir)


def test_uncontrolled_severity_taxonomy_is_rejected(repository, tmp_path):
    seed_dir = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed_dir)
    path = seed_dir / "taxonomy.json"
    taxonomy = json.loads(path.read_text(encoding="utf-8"))
    taxonomy["severity"].append("urgent")
    path.write_text(json.dumps(taxonomy), encoding="utf-8")
    with pytest.raises(ValueError, match="severity taxonomy"):
        seed_database(repository, seed_dir)


def test_held_out_queries_do_not_copy_tickets_and_use_approved_sources(repository):
    seed_database(repository)
    queries = json.loads((SEED_DIR.parents[1] / "evaluation" / "held_out_queries.json").read_text(encoding="utf-8"))
    complaints = {ticket.complaint.casefold() for ticket in repository.list_tickets()}
    eligible = {ticket.ticket_id for ticket in repository.list_tickets(evidence_only=True)}
    eligible |= {article.kb_id for article in repository.list_kb_articles(evidence_only=True)}
    assert len(queries) >= 12
    assert len({query["query_id"] for query in queries}) == len(queries)
    assert all(query["complaint"].casefold() not in complaints for query in queries)
    assert all(set(query["relevant_source_ids"]) <= eligible for query in queries)
