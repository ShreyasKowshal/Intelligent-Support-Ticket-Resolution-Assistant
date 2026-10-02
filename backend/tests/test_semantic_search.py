"""Fast search tests use a deterministic encoder; evaluation checks the real model."""

import hashlib
import json

import numpy as np
import pytest
from sqlalchemy import update
from sqlalchemy.engine import URL

from app.config import EMBEDDING_MODEL_NAME, EMBEDDING_RUNTIME_VERSION
from app.models import EmbeddingMetadata
from app.search import SentenceEncoder, SemanticSearch, embedding_version, normalize_vectors, ticket_embedding_text
from app.seed import seed_database
from app.storage import Repository, kb_articles as kb_table, tickets as tickets_table


class FakeEncoder:
    dimension = 4

    def __init__(self):
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls.append(texts)
        vectors = []
        for text in texts:
            lower = text.lower()
            if any(word in lower for word in ("broadband_connectivity", "dropping", "drops", "line-status")):
                vectors.append([4.0, 0.0, 0.0, 0.0])
            elif any(word in lower for word in ("billing_dispute", "invoice", "bill")):
                vectors.append([0.0, 4.0, 0.0, 0.0])
            elif any(word in lower for word in ("roaming", "abroad", "overseas")):
                vectors.append([0.0, 0.0, 4.0, 0.0])
            else:
                digest = hashlib.sha256(text.encode("utf-8")).digest()
                vectors.append([float(value + 1) for value in digest[:4]])
        return np.asarray(vectors, dtype=np.float32)


@pytest.fixture
def search_setup(tmp_path):
    repository = Repository(URL.create("sqlite", database=str(tmp_path / "search.db")))
    seed_database(repository)
    encoder = FakeEncoder()
    search = SemanticSearch(repository, encoder=encoder, index_dir=tmp_path / "indexes")
    yield repository, encoder, search
    repository.close()


def test_embedding_text_excludes_resolution_and_versions_change(search_setup):
    repository, _, _ = search_setup
    ticket = repository.get_ticket("T-001")
    assert ticket is not None
    text = ticket_embedding_text(ticket)
    assert ticket.complaint in text
    assert ticket.product in text and ticket.category in text
    assert ticket.resolution not in text
    assert embedding_version(text) != embedding_version(text + " changed")
    assert len(embedding_version(text)) <= 80


def test_normalization_rejects_bad_vectors():
    normalized = normalize_vectors(np.array([[3, 4], [0, 2]], dtype=np.float64))
    assert normalized.dtype == np.float32
    assert np.allclose(np.linalg.norm(normalized, axis=1), [1, 1])
    with pytest.raises(ValueError):
        normalize_vectors(np.array([[0, 0]], dtype=np.float32))


def test_onnx_model_is_loaded_once_per_encoder(monkeypatch, tmp_path):
    loaded = []

    class Model:
        embedding_size = 384

        def embed(self, texts, **kwargs):
            for _ in texts:
                yield np.array([3.0, 4.0] + [0.0] * 382, dtype=np.float32)

    def make_model(*, model_name, specific_model_path, threads, cuda, **kwargs):
        loaded.append((model_name, specific_model_path, threads, cuda))
        return Model()

    monkeypatch.setattr("app.search.snapshot_download", lambda **_kwargs: str(tmp_path / "pinned"))
    monkeypatch.setattr("app.search.TextEmbedding", make_model)
    encoder = SentenceEncoder(cache_dir=tmp_path / "cache")
    assert encoder.dimension == 384
    vectors = encoder.encode(["one", "two"])
    assert vectors.shape == (2, 384)
    assert np.allclose(vectors[:, :2], [[0.6, 0.8], [0.6, 0.8]])
    assert np.allclose(np.linalg.norm(vectors, axis=1), [1, 1])
    assert encoder.dimension == 384
    assert len(loaded) == 1
    assert loaded[0] == (EMBEDDING_MODEL_NAME, str(tmp_path / "pinned"), 1, False)


def test_old_runtime_vectors_and_index_are_rebuilt(search_setup):
    repository, encoder, search = search_setup
    ticket = repository.get_ticket("T-001")
    assert ticket is not None
    text = ticket_embedding_text(ticket)
    old_revision = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    old_hash = hashlib.sha256(f"{old_revision}:v1:{text}".encode()).hexdigest()
    old_version = f"{old_revision[:12]}-v1-{old_hash}"
    repository.save_embedding(EmbeddingMetadata(
        source_id=ticket.ticket_id, source_type="ticket", model_name=EMBEDDING_MODEL_NAME,
        model_version=old_version, vector_bytes=np.ones(4, dtype="<f4").tobytes(),
        updated_at=ticket.updated_at,
    ))
    search.build_indexes()
    assert old_version != embedding_version(text)
    assert any(text in batch for batch in encoder.calls)
    assert repository.get_embedding(ticket.ticket_id, "ticket", EMBEDDING_MODEL_NAME, old_version) is None
    assert repository.get_embedding(
        ticket.ticket_id, "ticket", EMBEDDING_MODEL_NAME, embedding_version(text)
    )

    manifest_path = search.index_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["runtime_version"] == EMBEDDING_RUNTIME_VERSION
    manifest["runtime_version"] = "sentence-transformers-pytorch"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    encoder.calls.clear()
    restarted = SemanticSearch(repository, encoder=encoder, index_dir=search.index_dir)
    assert restarted.load_or_build() == "rebuilt"
    assert encoder.calls == []  # Current ONNX vectors are reused; the old FAISS file is not.
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["runtime_version"] == EMBEDDING_RUNTIME_VERSION


def test_eligible_counts_and_durable_embedding_metadata(search_setup):
    repository, encoder, search = search_setup
    search.build_indexes()
    assert search.ticket_index.ntotal == 96
    assert search.kb_index.ntotal == 22
    assert len(search.ticket_ids) == 96 and len(set(search.ticket_ids)) == 96
    assert len(search.kb_ids) == 22 and len(set(search.kb_ids)) == 22
    assert "T-009" not in search.ticket_ids
    assert "T-010" not in search.ticket_ids
    assert "KB-020" not in search.kb_ids
    assert "KB-024" not in search.kb_ids
    ticket = repository.get_ticket("T-001")
    assert ticket is not None
    stored = repository.get_embedding(
        "T-001", "ticket", EMBEDDING_MODEL_NAME, embedding_version(ticket_embedding_text(ticket))
    )
    assert stored is not None and stored.vector_bytes is not None
    assert len(stored.vector_bytes) == encoder.dimension * 4
    assert stored.updated_at == ticket.updated_at
    assert repository.get_embedding("T-009", "ticket", EMBEDDING_MODEL_NAME, embedding_version("x")) is None


def test_top_k_and_id_mapping_survive_reload(search_setup):
    repository, encoder, search = search_setup
    search.build_indexes()
    first = search.search("My broadband keeps dropping every evening", ticket_k=3, kb_k=2)
    assert len(first.tickets) == 3 and len(first.kb_articles) == 2
    assert all(item.source_id in search.ticket_ids for item in first.tickets)
    assert all(item.source_id in search.kb_ids for item in first.kb_articles)
    assert all(item.resolution for item in first.tickets)
    assert all(-1.001 <= item.similarity_score <= 1.001 for item in first.tickets)

    reloaded = SemanticSearch(repository, encoder=encoder, index_dir=search.index_dir)
    assert reloaded.load_or_build() == "loaded"
    second = reloaded.search("My broadband keeps dropping every evening", ticket_k=3, kb_k=2)
    assert first == second
    assert reloaded.ticket_ids == search.ticket_ids
    assert reloaded.kb_ids == search.kb_ids
    all_results = reloaded.search("Broadband drops", ticket_k=200, kb_k=200)
    assert len(all_results.tickets) == 96
    assert len(all_results.kb_articles) == 22


def test_missing_index_rebuilds_from_stored_vectors_without_encoding(search_setup):
    repository, encoder, search = search_setup
    search.build_indexes()
    encoder.calls.clear()
    (search.index_dir / "tickets.faiss").unlink()
    replacement = SemanticSearch(repository, encoder=encoder, index_dir=search.index_dir)
    assert replacement.load_or_build() == "rebuilt"
    assert replacement.ticket_index.ntotal == 96
    assert encoder.calls == []


def test_new_approved_ticket_can_be_refreshed_later(search_setup):
    repository, encoder, search = search_setup
    search.build_indexes()
    ticket = repository.get_ticket("T-001")
    assert ticket is not None
    repository.add_ticket(ticket.model_copy(update={"ticket_id": "T-121", "complaint": "Evening line drops after a reboot."}))
    encoder.calls.clear()
    search.refresh_indexes()
    assert search.ticket_index.ntotal == 97
    assert "T-121" in search.ticket_ids
    assert sum(len(batch) for batch in encoder.calls) == 1


def test_revoked_approval_invalidates_saved_index(search_setup):
    repository, encoder, search = search_setup
    search.build_indexes()
    with repository.engine.begin() as connection:
        connection.execute(
            update(tickets_table).where(tickets_table.c.ticket_id == "T-001").values(approved=False)
        )
        connection.execute(
            update(kb_table).where(kb_table.c.kb_id == "KB-001").values(approved=False)
        )
    assert "T-001" not in {item.source_id for item in search.search("broadband", ticket_k=100).tickets}
    assert "KB-001" not in {item.source_id for item in search.search("broadband", kb_k=100).kb_articles}
    reloaded = SemanticSearch(repository, encoder=encoder, index_dir=search.index_dir)
    assert reloaded.load_or_build() == "loaded"  # The active search already refreshed the saved files.
    assert reloaded.ticket_index.ntotal == 95
    assert reloaded.kb_index.ntotal == 21
    assert "T-001" not in reloaded.ticket_ids
    assert "KB-001" not in reloaded.kb_ids
    assert "T-001" not in {item.source_id for item in reloaded.search("broadband", ticket_k=100).tickets}


def test_empty_query_and_invalid_top_k(search_setup):
    _, _, search = search_setup
    search.build_indexes()
    with pytest.raises(ValueError, match="complaint"):
        search.search("   ")
    for invalid in (0, -1, True, 1.5, "3"):
        with pytest.raises(ValueError, match="Top-K"):
            search.search("Broadband drops", ticket_k=invalid)
