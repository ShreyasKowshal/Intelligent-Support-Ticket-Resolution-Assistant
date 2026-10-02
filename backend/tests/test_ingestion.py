"""Evolving records retain evidence eligibility and durable search mappings."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.engine import URL

from app.analysis import ComplaintAnalysis, ComplaintAnalyzer
from app.ingestion import IngestionService
from app import ingest
from app.llm import FakeLLMClient
from app.rag import GroundingError, RAGGenerator
from app.models import KnowledgeBaseArticle, SupportTicket, TaxonomyValue
from app.search import SemanticSearch, embedding_version, kb_embedding_text, ticket_embedding_text
from app.seed import seed_database
from app.storage import Repository, embeddings
from app.taxonomy import normalize_sentiment, normalize_severity
from app.config import EMBEDDING_MODEL_NAME


NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


class FakeEncoder:
    dimension = 4

    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.extend(texts)
        return np.asarray([
            [1, 0, 0, 0] if "opticalpulse" in text.lower() else [0, 1, 0, 0]
            for text in texts
        ], dtype=np.float32)


@pytest.fixture
def setup(tmp_path):
    url = URL.create("sqlite", database=str(tmp_path / "support.db"))
    repository = Repository(url)
    seed_database(repository)
    encoder = FakeEncoder()
    search = SemanticSearch(repository, encoder=encoder, index_dir=tmp_path / "indexes")
    search.load_or_build()
    yield repository, encoder, search, IngestionService(repository, search)
    repository.close()


def ticket(**updates):
    data = dict(
        ticket_id="T-121", complaint="The opticalpulse modem signal is missing",
        product="broadband", category="broadband_connectivity", severity="HIGH",
        sentiment="FRUSTRATED", resolution="", status="open", approved=False,
        created_at=NOW, updated_at=NOW,
    )
    data.update(updates)
    return SupportTicket.model_validate(data)


def article(**updates):
    data = dict(
        kb_id="KB-025", title="Opticalpulse checks", content="Check the opticalpulse indicator.",
        category="broadband_connectivity", approved=False, version=1,
        created_at=NOW, updated_at=NOW,
    )
    data.update(updates)
    return KnowledgeBaseArticle.model_validate(data)


def ids(search):
    result = search.search("opticalpulse", ticket_k=200, kb_k=200)
    return {item.source_id for item in result.tickets}, {item.source_id for item in result.kb_articles}


def test_unresolved_and_unapproved_tickets_stay_out_of_evidence(setup):
    repository, encoder, search, service = setup
    before = len(encoder.calls)
    assert service.upsert_ticket(ticket()).index_refreshed is False
    assert repository.get_ticket("T-121") is not None
    assert len(encoder.calls) == before
    assert "T-121" not in search.ticket_ids and "T-121" not in ids(search)[0]
    unapproved = ticket(status="resolved", resolution="Replace the opticalpulse cable.",
                        updated_at=NOW + timedelta(minutes=1))
    assert service.upsert_ticket(unapproved).index_refreshed is False
    assert "T-121" not in ids(search)[0]


def test_approval_resolution_and_revocations_refresh_search(setup):
    repository, encoder, search, service = setup
    service.upsert_ticket(ticket())
    approved = ticket(status="resolved", approved=True, resolution="Inspect the opticalpulse cable.",
                      updated_at=NOW + timedelta(minutes=1))
    outcome = service.upsert_ticket(approved)
    assert outcome.eligibility_changed and outcome.index_refreshed
    assert "T-121" in ids(search)[0] and search.ticket_index.ntotal == 97
    assert search.search("opticalpulse").tickets[0].source_id == "T-121"
    revoked = approved.model_copy(update={"approved": False, "updated_at": NOW + timedelta(minutes=2)})
    assert service.upsert_ticket(revoked).index_refreshed
    assert repository.get_ticket("T-121") is not None and "T-121" not in ids(search)[0]
    reapproved = approved.model_copy(update={"updated_at": NOW + timedelta(minutes=3)})
    service.upsert_ticket(reapproved)
    opened = approved.model_copy(update={"status": "open", "approved": False,
                                          "resolution": "", "updated_at": NOW + timedelta(minutes=4)})
    assert service.upsert_ticket(opened).index_refreshed
    assert repository.get_ticket("T-121") is not None and "T-121" not in ids(search)[0]


def test_content_update_refreshes_embedding_without_duplicates(setup):
    repository, encoder, search, service = setup
    original = ticket(status="resolved", approved=True, resolution="Inspect light.")
    service.upsert_ticket(original)
    first_version = embedding_version(ticket_embedding_text(original))
    old_count = len(encoder.calls)
    changed = original.model_copy(update={"complaint": "The opticalpulse red alarm flashes",
                                          "updated_at": NOW + timedelta(minutes=1)})
    result = service.upsert_ticket(changed)
    assert result.text_changed and result.index_refreshed
    assert len(encoder.calls) == old_count + 1
    assert repository.get_embedding("T-121", "ticket", EMBEDDING_MODEL_NAME, first_version) is None
    assert search.search("opticalpulse red alarm").tickets[0].source_id == "T-121"
    with repository.engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(embeddings).where(
            embeddings.c.source_id == "T-121", embeddings.c.source_type == "ticket"
        ))
    assert count == 1
    old_count = len(encoder.calls)
    resolution_only = changed.model_copy(update={"resolution": "New approved guidance.",
                                                "updated_at": NOW + timedelta(minutes=2)})
    assert not service.upsert_ticket(resolution_only).index_refreshed
    assert len(encoder.calls) == old_count
    assert search.search("opticalpulse").tickets[0].resolution == "New approved guidance."


def test_restart_rebuilds_ticket_and_kb_from_durable_vectors(setup):
    repository, encoder, search, service = setup
    service.upsert_ticket(ticket(status="resolved", approved=True, resolution="Check opticalpulse."))
    service.upsert_kb_article(article(approved=True))
    assert repository.get_embedding("T-121", "ticket", EMBEDDING_MODEL_NAME,
                                    embedding_version(ticket_embedding_text(repository.get_ticket("T-121"))))
    encoder.calls.clear()
    (search.index_dir / "tickets.faiss").unlink()
    reopened = Repository(repository.engine.url)
    try:
        restarted = SemanticSearch(reopened, encoder=encoder, index_dir=search.index_dir)
        assert restarted.load_or_build() == "rebuilt"
        assert encoder.calls == []
        assert "T-121" in ids(restarted)[0] and "KB-025" in ids(restarted)[1]
    finally:
        reopened.close()


def test_kb_insert_update_and_revoke(setup):
    repository, encoder, search, service = setup
    assert not service.upsert_kb_article(article()).index_refreshed
    assert "KB-025" not in ids(search)[1]
    approved = article(approved=True, updated_at=NOW + timedelta(minutes=1))
    assert service.upsert_kb_article(approved).index_refreshed
    assert "KB-025" in ids(search)[1]
    old_version = embedding_version(kb_embedding_text(approved))
    updated = article(approved=True, content="Inspect the opticalpulse red light.", version=2,
                      updated_at=NOW + timedelta(minutes=2))
    assert service.upsert_kb_article(updated).text_changed
    assert repository.get_embedding("KB-025", "kb", EMBEDDING_MODEL_NAME, old_version) is None
    assert search.search("opticalpulse red light").kb_articles[0].source_id == "KB-025"
    reopened = Repository(repository.engine.url)
    try:
        restarted = SemanticSearch(reopened, encoder=encoder, index_dir=search.index_dir)
        assert restarted.load_or_build() == "loaded"
        assert reopened.get_kb_article("KB-025").content == updated.content
        assert restarted.search("opticalpulse red light").kb_articles[0].source_id == "KB-025"
    finally:
        reopened.close()
    assert service.upsert_kb_article(updated.model_copy(update={"approved": False,
        "updated_at": NOW + timedelta(minutes=3)})).index_refreshed
    assert repository.get_kb_article("KB-025") is not None and "KB-025" not in ids(search)[1]


def test_taxonomy_review_and_dynamic_analysis(setup):
    repository, _, _, service = setup
    response = {
        "intent": "restore a new service", "category": "opticalpulse_fault", "product": "broadband",
        "severity": "HIGH", "sentiment": "ANGRY", "confidence": 0.8,
        "needs_review": False, "rationale": "A new optical fault is reported.",
    }
    fake = FakeLLMClient(response)
    analyzer = ComplaintAnalyzer.from_repository(fake, repository)
    before = analyzer.analyze("My opticalpulse service fails.")
    assert before.category == "other" and before.needs_review
    with pytest.raises(ValueError, match="reviewed_by"):
        service.add_reviewed_taxonomy_value(TaxonomyValue(kind="category", value="opticalpulse_fault"), "")
    service.add_reviewed_taxonomy_value(TaxonomyValue(kind="category", value="opticalpulse_fault"), "admin")
    assert "opticalpulse_fault" in repository.list_taxonomy("category")
    after = analyzer.analyze("My opticalpulse service fails.")
    assert after.category == "opticalpulse_fault" and not after.needs_review
    service.add_reviewed_taxonomy_value(TaxonomyValue(kind="product", value="satellite"), "admin")
    assert "satellite" in repository.list_taxonomy("product")


def test_canonical_severity_and_sentiment(setup):
    repository, _, _, service = setup
    stored = ticket(severity="HIGH", sentiment="ANGRY")
    service.upsert_ticket(stored)
    assert repository.get_ticket("T-121").severity == "high"
    assert repository.get_ticket("T-121").sentiment == "negative"
    assert normalize_severity(" critical ") == "critical"
    assert normalize_sentiment("FRUSTRATED") == "frustrated"
    assert TaxonomyValue(kind="severity", value="HIGH").value == "high"
    assert TaxonomyValue(kind="sentiment", value="ANGRY").value == "negative"


def test_stable_id_and_invalid_updates_rejected(setup):
    repository, _, _, service = setup
    original = ticket()
    assert service.upsert_ticket(original).change == "inserted"
    assert service.upsert_ticket(original).change == "unchanged"
    with pytest.raises(ValueError, match="created_at"):
        service.upsert_ticket(original.model_copy(update={
            "created_at": NOW + timedelta(seconds=1), "updated_at": NOW + timedelta(seconds=2)
        }))
    with pytest.raises(ValueError, match="updated_at"):
        service.upsert_ticket(original.model_copy(update={"complaint": "changed"}))
    with pytest.raises(ValidationError):
        service.upsert_ticket(original.model_copy(update={"ticket_id": "bad"}))
    with pytest.raises(ValidationError):
        service.upsert_ticket(original.model_copy(update={"approved": True}))
    service.upsert_kb_article(article(approved=True))
    with pytest.raises(ValueError, match="version"):
        service.upsert_kb_article(article(approved=True, content="changed",
            updated_at=NOW + timedelta(minutes=1)))


def test_external_update_is_seen_by_existing_search(setup):
    repository, encoder, search, _ = setup
    separate = SemanticSearch(repository, encoder=encoder, index_dir=search.index_dir)
    separate.load_or_build()
    IngestionService(repository, separate).upsert_ticket(
        ticket(status="resolved", approved=True, resolution="Check opticalpulse."))
    assert search.search("opticalpulse").tickets[0].source_id == "T-121"


def test_rag_cannot_cite_new_unapproved_ticket(setup):
    _, _, search, service = setup
    service.upsert_ticket(ticket(status="resolved", resolution="Check opticalpulse."))
    analysis = ComplaintAnalysis(
        intent="restore service", category="broadband_connectivity", product="broadband",
        severity="HIGH", sentiment="FRUSTRATED", confidence=0.8,
        needs_review=False, rationale="The optical service is down.",
    )
    cited = {
        "problem_summary": "The optical service is down.",
        "resolution_steps": [{"step_number": 1, "action": "Check approved guidance.",
                              "source_ids": ["T-121"]}],
        "escalation_recommendation": "Escalate if needed.",
        "confidence_or_evidence_note": "One historical ticket supports the step.",
        "sources_used": ["T-121"], "insufficient_evidence": False,
    }
    generator = RAGGenerator(FakeLLMClient({}, cited), min_similarity=-1)
    results = search.search("opticalpulse")
    assert "T-121" not in {item.source_id for item in results.tickets}
    with pytest.raises(GroundingError, match="outside retrieved evidence"):
        generator.generate("opticalpulse", analysis, results.tickets, results.kb_articles)
    service.upsert_ticket(ticket(status="resolved", approved=True,
                                 resolution="Check opticalpulse.", updated_at=NOW + timedelta(minutes=1)))
    results = search.search("opticalpulse")
    assert generator.generate("opticalpulse", analysis, results.tickets,
                              results.kb_articles).sources_used == ["T-121"]


def test_cli_validation_does_not_echo_complaint(tmp_path, monkeypatch, capsys):
    secret_text = "private customer complaint token"
    path = tmp_path / "invalid.json"
    path.write_text(ticket(complaint=secret_text).model_dump_json(), encoding="utf-8")
    payload = path.read_text(encoding="utf-8").replace('"status":"open"', '"status":"invalid"')
    path.write_text(payload, encoding="utf-8")
    url = URL.create("sqlite", database=str(tmp_path / "cli.db"))
    monkeypatch.setattr(ingest, "Repository", lambda: Repository(url))
    monkeypatch.setattr("sys.argv", ["ingest", "ticket", str(path)])
    with pytest.raises(SystemExit):
        ingest.main()
    output = capsys.readouterr()
    assert secret_text not in output.err
    assert "status" in output.err
