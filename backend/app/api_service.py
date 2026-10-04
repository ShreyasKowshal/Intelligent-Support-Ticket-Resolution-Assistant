"""Reuse the existing application services for the lifetime of an API process."""

import hmac
import os
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv

from app.analysis import ComplaintAnalysis, ComplaintAnalyzer
from app.actionability import is_non_actionable_complaint
from app.gemini_client import GeminiClient, MissingApiKeyError
from app.ingestion import IngestionService, UpdateOutcome
from app.llm import LLMClient
from app.models import KnowledgeBaseArticle, SupportTicket, TaxonomyValue
from app.rag import RAGGenerator, RAGResolution
from app.search import SearchResults, SemanticSearch
from app.storage import Repository


class AdminConfigurationError(RuntimeError):
    """Admin updates are disabled until a secret is configured."""


class UnauthorizedAdminError(RuntimeError):
    """The supplied admin secret did not match."""


class ApiServices:
    def __init__(
        self, repository: Repository, search: SemanticSearch, client: LLMClient | None,
        admin_key: str | None = None,
    ) -> None:
        self.repository = repository
        self.search = search
        self.client = client
        self.admin_key = admin_key.strip() if admin_key else None
        self.ingestion = IngestionService(repository, search)
        self.analyzer: ComplaintAnalyzer | None = None
        self.generator = RAGGenerator(client) if client is not None else None
        # Search index refresh and analyzer taxonomy updates mutate shared state.
        self._lock = RLock()

    def close(self) -> None:
        if self.client is not None and callable(getattr(self.client, "close", None)):
            self.client.close()
        self.repository.close()

    def ready(self) -> dict[str, bool | str]:
        database = search_index = embedding_model = False
        with self._lock:
            try:
                self.repository.list_taxonomy("category")
                database = True
                has_evidence = bool(
                    self.repository.list_tickets(evidence_only=True)
                    or self.repository.list_kb_articles(evidence_only=True)
                )
                if has_evidence:
                    self._ensure_search()
                    search_index = self.search.ticket_index is not None and self.search.kb_index is not None
                    embedding_model = search_index
            except Exception:
                # Readiness reports status, never exception text or configuration.
                pass
        healthy = database and search_index and embedding_model and self.client is not None
        return {
            "status": "ready" if healthy else "not_ready",
            "database": database,
            "search_index": search_index,
            "embedding_model": embedding_model,
            "gemini_configured": self.client is not None,
        }

    def analyze(self, complaint: str) -> ComplaintAnalysis:
        with self._lock:
            return self._analyze(complaint)

    def search_complaint(
        self, complaint: str, ticket_k: int | None = None, kb_k: int | None = None,
    ) -> SearchResults:
        with self._lock:
            return self._search(complaint, ticket_k, kb_k)

    def resolve(self, complaint: str) -> tuple[ComplaintAnalysis, SearchResults, RAGResolution, bool]:
        with self._lock:
            analysis = self._analyze(complaint)
            if is_non_actionable_complaint(complaint, analysis):
                return analysis, SearchResults([], []), RAGResolution(
                    problem_summary="No clear telecom issue was identified.",
                    resolution_steps=[],
                    escalation_recommendation=(
                        "No telecom service issue was identified. Please describe the telecom service "
                        "problem you need help with."
                    ),
                    confidence_or_evidence_note=(
                        "Retrieval was skipped because the message did not describe an actionable telecom problem."
                    ),
                    sources_used=[],
                    insufficient_evidence=True,
                ), True
            results = self._search(complaint)
            assert self.generator is not None
            resolution: RAGResolution = self.generator.generate(
                complaint, analysis, results.tickets, results.kb_articles
            )
            return analysis, results, resolution, False

    def authorize_admin(self, supplied_key: str | None) -> None:
        if not self.admin_key:
            raise AdminConfigurationError("Admin API key is not configured")
        if not supplied_key or not hmac.compare_digest(supplied_key, self.admin_key):
            raise UnauthorizedAdminError("Invalid admin key")

    def upsert_ticket(self, ticket: SupportTicket) -> UpdateOutcome:
        with self._lock:
            return self.ingestion.upsert_ticket(ticket)

    def upsert_kb_article(self, article: KnowledgeBaseArticle) -> UpdateOutcome:
        with self._lock:
            return self.ingestion.upsert_kb_article(article)

    def add_taxonomy_value(self, item: TaxonomyValue, reviewed_by: str) -> None:
        with self._lock:
            self.ingestion.add_reviewed_taxonomy_value(item, reviewed_by)

    def _analyze(self, complaint: str) -> ComplaintAnalysis:
        if self.client is None:
            raise MissingApiKeyError("GEMINI_API_KEY is missing")
        if self.analyzer is None:
            self.analyzer = ComplaintAnalyzer.from_repository(self.client, self.repository)
        return self.analyzer.analyze(complaint)

    def _ensure_search(self) -> None:
        if self.search.ticket_index is None or self.search.kb_index is None:
            self.search.load_or_build()

    def _search(self, complaint: str, ticket_k: int | None = None, kb_k: int | None = None) -> SearchResults:
        self._ensure_search()
        return self.search.search(complaint, ticket_k, kb_k)


def build_services() -> ApiServices:
    """Initialize inexpensive resources; load the embedding model on first search."""
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    repository = Repository()
    client = None
    try:
        repository.initialize()
        try:
            client = GeminiClient()
        except MissingApiKeyError:
            pass
        search = SemanticSearch(repository)
        return ApiServices(repository, search, client, os.getenv("ADMIN_API_KEY"))
    except Exception:
        if client is not None:
            client.close()
        repository.close()
        raise
