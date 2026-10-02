"""CPU semantic search over approved ticket and KB evidence."""

import hashlib
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from uuid import uuid4

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import (
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_REVISION,
    EMBEDDING_TEXT_VERSION,
    get_search_top_k,
)
from app.models import EmbeddingMetadata, KnowledgeBaseArticle, SupportTicket
from app.storage import Repository

DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "indexes"


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """Return contiguous float32 unit vectors for FAISS inner-product search."""
    result = np.asarray(vectors, dtype=np.float32)
    if result.ndim != 2 or result.shape[1] == 0 or not np.isfinite(result).all():
        raise ValueError("embeddings must be a finite two-dimensional matrix")
    lengths = np.linalg.norm(result, axis=1, keepdims=True)
    if np.any(lengths == 0):
        raise ValueError("embedding vectors cannot have zero length")
    return np.ascontiguousarray(result / lengths)


def ticket_embedding_text(ticket: SupportTicket) -> str:
    """Use complaint context, never the historical resolution."""
    return f"Complaint: {ticket.complaint}\nProduct: {ticket.product}\nCategory: {ticket.category}"


def kb_embedding_text(article: KnowledgeBaseArticle) -> str:
    return f"Title: {article.title}\nContent: {article.content}\nCategory: {article.category}"


def embedding_version(text: str) -> str:
    """Tie stored vectors to the pinned model and exact source text."""
    digest = hashlib.sha256(
        f"{EMBEDDING_MODEL_REVISION}:{EMBEDDING_TEXT_VERSION}:{text}".encode("utf-8")
    ).hexdigest()
    return f"{EMBEDDING_MODEL_REVISION[:12]}-{EMBEDDING_TEXT_VERSION}-{digest}"


class SentenceEncoder:
    """Load one pinned model lazily and reuse it for indexing and queries."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or Path(__file__).resolve().parents[1] / "data" / "model_cache"

    @cached_property
    def model(self) -> SentenceTransformer:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            return SentenceTransformer(
                EMBEDDING_MODEL_NAME,
                revision=EMBEDDING_MODEL_REVISION,
                cache_folder=str(self.cache_dir),
                device="cpu",
                trust_remote_code=False,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not load the pinned embedding model. Check the first-run download "
                "connection or the local model cache."
            ) from exc

    @property
    def dimension(self) -> int:
        dimension = self.model.get_embedding_dimension()
        if dimension is None:
            raise RuntimeError("embedding model did not report a vector dimension")
        return int(dimension)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return normalize_vectors(vectors)


@dataclass(frozen=True)
class TicketMatch:
    source_id: str
    complaint: str
    product: str
    category: str
    resolution: str
    similarity_score: float


@dataclass(frozen=True)
class KBMatch:
    source_id: str
    title: str
    content: str
    category: str
    similarity_score: float


@dataclass(frozen=True)
class SearchResults:
    tickets: list[TicketMatch]
    kb_articles: list[KBMatch]


class SemanticSearch:
    def __init__(
        self,
        repository: Repository,
        encoder: SentenceEncoder | None = None,
        index_dir: Path = DEFAULT_INDEX_DIR,
    ) -> None:
        self.repository = repository
        self.encoder = encoder or SentenceEncoder()
        self.index_dir = Path(index_dir)
        self.ticket_index: faiss.Index | None = None
        self.kb_index: faiss.Index | None = None
        self.ticket_ids: list[str] = []
        self.kb_ids: list[str] = []
        self._signature: str | None = None

    def build_indexes(self) -> None:
        """Reuse matching durable vectors, encode missing ones, and save fresh indexes."""
        ticket_records = self.repository.list_tickets(evidence_only=True)
        kb_records = self.repository.list_kb_articles(evidence_only=True)
        dimension = self.encoder.dimension
        ticket_vectors = self._vectors(
            [record.ticket_id for record in ticket_records],
            [ticket_embedding_text(record) for record in ticket_records],
            [record.updated_at for record in ticket_records],
            "ticket",
            dimension,
        )
        kb_vectors = self._vectors(
            [record.kb_id for record in kb_records],
            [kb_embedding_text(record) for record in kb_records],
            [record.updated_at for record in kb_records],
            "kb",
            dimension,
        )
        self.ticket_index = faiss.IndexFlatIP(dimension)
        self.kb_index = faiss.IndexFlatIP(dimension)
        if len(ticket_records):
            self.ticket_index.add(ticket_vectors)
        if len(kb_records):
            self.kb_index.add(kb_vectors)
        self._set_mapping(ticket_records, kb_records)
        signature = self._source_signature(ticket_records, kb_records)
        self._save_indexes(signature)
        self._signature = signature

    def refresh_indexes(self) -> None:
        """Rebuild from durable eligible records, reusing unchanged vectors."""
        self.build_indexes()

    def invalidate(self) -> None:
        """Prevent serving old in-memory vectors after a durable write."""
        self.ticket_index = None
        self.kb_index = None
        self.ticket_ids = []
        self.kb_ids = []
        self._signature = None

    def load_or_build(self) -> str:
        """Load verified files, or rebuild from the repository when absent or stale."""
        ticket_records = self.repository.list_tickets(evidence_only=True)
        kb_records = self.repository.list_kb_articles(evidence_only=True)
        if self._try_load(ticket_records, kb_records):
            self._signature = self._source_signature(ticket_records, kb_records)
            return "loaded"
        self.build_indexes()
        return "rebuilt"

    def search(
        self, complaint: str, ticket_k: int | None = None, kb_k: int | None = None
    ) -> SearchResults:
        if not complaint or not complaint.strip():
            raise ValueError("complaint must contain text")
        defaults = get_search_top_k()
        ticket_k = defaults[0] if ticket_k is None else ticket_k
        kb_k = defaults[1] if kb_k is None else kb_k
        for value in (ticket_k, kb_k):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("Top-K values must be positive integers")
        if self.ticket_index is None or self.kb_index is None:
            raise RuntimeError("search indexes are not ready; call load_or_build first")
        current_signature = self._source_signature(
            self.repository.list_tickets(evidence_only=True),
            self.repository.list_kb_articles(evidence_only=True),
        )
        if current_signature != self._signature:
            self.load_or_build()
        query_vector = normalize_vectors(self.encoder.encode([complaint.strip()]))
        ticket_scores, ticket_positions = self.ticket_index.search(query_vector, ticket_k)
        kb_scores, kb_positions = self.kb_index.search(query_vector, kb_k)
        ticket_matches = []
        for score, position in zip(ticket_scores[0], ticket_positions[0]):
            if position < 0:
                continue
            source_id = self.ticket_ids[position]
            record = self.repository.get_ticket(source_id, evidence_only=True)
            if record is not None:
                ticket_matches.append(TicketMatch(
                    source_id=source_id,
                    complaint=record.complaint,
                    product=record.product,
                    category=record.category,
                    resolution=record.resolution,
                    similarity_score=float(score),
                ))
        kb_matches = []
        for score, position in zip(kb_scores[0], kb_positions[0]):
            if position < 0:
                continue
            source_id = self.kb_ids[position]
            record = self.repository.get_kb_article(source_id, evidence_only=True)
            if record is not None:
                kb_matches.append(KBMatch(
                    source_id=source_id,
                    title=record.title,
                    content=record.content,
                    category=record.category,
                    similarity_score=float(score),
                ))
        return SearchResults(tickets=ticket_matches, kb_articles=kb_matches)

    def _vectors(
        self, ids: list[str], texts: list[str], timestamps: list, source_type: str, dimension: int
    ) -> np.ndarray:
        if not ids:
            return np.empty((0, dimension), dtype=np.float32)
        vectors: list[np.ndarray | None] = [None] * len(ids)
        missing: list[int] = []
        versions = [embedding_version(text) for text in texts]
        for position, source_id in enumerate(ids):
            stored = self.repository.get_embedding(
                source_id, source_type, EMBEDDING_MODEL_NAME, versions[position]
            )
            if stored and stored.vector_bytes:
                candidate = np.frombuffer(stored.vector_bytes, dtype="<f4")
                if candidate.size == dimension and np.isfinite(candidate).all() and np.linalg.norm(candidate) > 0:
                    vectors[position] = normalize_vectors(candidate.reshape(1, -1))[0]
                    if stored.updated_at != timestamps[position]:
                        self.repository.save_embedding(stored.model_copy(update={"updated_at": timestamps[position]}))
                    continue
            missing.append(position)
        if missing:
            encoded = normalize_vectors(self.encoder.encode([texts[position] for position in missing]))
            if encoded.shape != (len(missing), dimension):
                raise RuntimeError("embedding model returned an unexpected vector shape")
            for row, position in enumerate(missing):
                vector = encoded[row]
                vectors[position] = vector
                self.repository.save_embedding(
                    EmbeddingMetadata(
                        source_id=ids[position],
                        source_type=source_type,
                        model_name=EMBEDDING_MODEL_NAME,
                        model_version=versions[position],
                        vector_bytes=vector.astype("<f4", copy=False).tobytes(),
                        updated_at=timestamps[position],
                    )
                )
        return np.ascontiguousarray(np.stack(vectors).astype(np.float32))

    def _set_mapping(
        self, ticket_records: list[SupportTicket], kb_records: list[KnowledgeBaseArticle]
    ) -> None:
        self.ticket_ids = [record.ticket_id for record in ticket_records]
        self.kb_ids = [record.kb_id for record in kb_records]

    @staticmethod
    def _source_signature(
        ticket_records: list[SupportTicket], kb_records: list[KnowledgeBaseArticle]
    ) -> str:
        entries = [
            ("ticket", record.ticket_id, record.updated_at.isoformat(), embedding_version(ticket_embedding_text(record)))
            for record in ticket_records
        ] + [
            ("kb", record.kb_id, record.updated_at.isoformat(), record.version, embedding_version(kb_embedding_text(record)))
            for record in kb_records
        ]
        return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _save_indexes(self, signature: str) -> None:
        assert self.ticket_index is not None and self.kb_index is not None
        self.index_dir.mkdir(parents=True, exist_ok=True)
        ticket_path = self.index_dir / "tickets.faiss"
        kb_path = self.index_dir / "kb.faiss"
        token = uuid4().hex
        ticket_temp = self.index_dir / f"tickets.{token}.tmp"
        kb_temp = self.index_dir / f"kb.{token}.tmp"
        faiss.write_index(self.ticket_index, str(ticket_temp))
        faiss.write_index(self.kb_index, str(kb_temp))
        ticket_temp.replace(ticket_path)
        kb_temp.replace(kb_path)
        manifest = {
            "format": 1,
            "model_name": EMBEDDING_MODEL_NAME,
            "model_revision": EMBEDDING_MODEL_REVISION,
            "text_version": EMBEDDING_TEXT_VERSION,
            "dimension": self.ticket_index.d,
            "source_signature": signature,
            "ticket_ids": self.ticket_ids,
            "kb_ids": self.kb_ids,
            "ticket_sha256": self._file_hash(ticket_path),
            "kb_sha256": self._file_hash(kb_path),
        }
        manifest_temp = self.index_dir / f"manifest.{token}.tmp"
        manifest_temp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest_temp.replace(self.index_dir / "manifest.json")

    def _try_load(
        self, ticket_records: list[SupportTicket], kb_records: list[KnowledgeBaseArticle]
    ) -> bool:
        manifest_path = self.index_dir / "manifest.json"
        ticket_path = self.index_dir / "tickets.faiss"
        kb_path = self.index_dir / "kb.faiss"
        if not all(path.is_file() for path in (manifest_path, ticket_path, kb_path)):
            return False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            dimension = self.encoder.dimension
            expected = {
                "format": 1,
                "model_name": EMBEDDING_MODEL_NAME,
                "model_revision": EMBEDDING_MODEL_REVISION,
                "text_version": EMBEDDING_TEXT_VERSION,
                "dimension": dimension,
                "source_signature": self._source_signature(ticket_records, kb_records),
                "ticket_ids": [record.ticket_id for record in ticket_records],
                "kb_ids": [record.kb_id for record in kb_records],
                "ticket_sha256": self._file_hash(ticket_path),
                "kb_sha256": self._file_hash(kb_path),
            }
            if manifest != expected:
                return False
            ticket_index = faiss.read_index(str(ticket_path))
            kb_index = faiss.read_index(str(kb_path))
            if (
                ticket_index.d != dimension or kb_index.d != dimension
                or ticket_index.ntotal != len(ticket_records)
                or kb_index.ntotal != len(kb_records)
                or ticket_index.metric_type != faiss.METRIC_INNER_PRODUCT
                or kb_index.metric_type != faiss.METRIC_INNER_PRODUCT
            ):
                return False
            self.ticket_index = ticket_index
            self.kb_index = kb_index
            self._set_mapping(ticket_records, kb_records)
            return True
        except (OSError, ValueError, RuntimeError, TypeError, json.JSONDecodeError):
            return False
