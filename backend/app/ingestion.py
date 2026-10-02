"""Controlled updates for reviewed support records and taxonomy."""

from dataclasses import dataclass

from app.models import KnowledgeBaseArticle, SupportTicket, TaxonomyValue
from app.search import SemanticSearch, kb_embedding_text, ticket_embedding_text
from app.storage import Repository


@dataclass(frozen=True)
class UpdateOutcome:
    change: str
    text_changed: bool
    eligibility_changed: bool
    index_refreshed: bool


class IngestionService:
    def __init__(self, repository: Repository, search: SemanticSearch) -> None:
        self.repository = repository
        self.search = search

    def upsert_ticket(self, ticket: SupportTicket) -> UpdateOutcome:
        ticket = SupportTicket.model_validate(ticket.model_dump())
        old = self.repository.get_ticket(ticket.ticket_id)
        old_eligible = old is not None and old.status == "resolved" and old.approved
        new_eligible = ticket.status == "resolved" and ticket.approved
        text_changed = old is None or ticket_embedding_text(old) != ticket_embedding_text(ticket)
        eligibility_changed = old_eligible != new_eligible
        change = self.repository.upsert_ticket(ticket)
        refresh = change != "unchanged" and (
            eligibility_changed or (new_eligible and text_changed)
        )
        if refresh:
            self.search.invalidate()
            self.search.refresh_indexes()
        return UpdateOutcome(change, text_changed, eligibility_changed, refresh)

    def upsert_kb_article(self, article: KnowledgeBaseArticle) -> UpdateOutcome:
        article = KnowledgeBaseArticle.model_validate(article.model_dump())
        old = self.repository.get_kb_article(article.kb_id)
        old_eligible = old is not None and old.approved
        new_eligible = article.approved
        text_changed = old is None or kb_embedding_text(old) != kb_embedding_text(article)
        eligibility_changed = old_eligible != new_eligible
        change = self.repository.upsert_kb_article(article)
        refresh = change != "unchanged" and (
            eligibility_changed or (new_eligible and text_changed)
        )
        if refresh:
            self.search.invalidate()
            self.search.refresh_indexes()
        return UpdateOutcome(change, text_changed, eligibility_changed, refresh)

    def add_reviewed_taxonomy_value(self, item: TaxonomyValue, reviewed_by: str) -> None:
        if not isinstance(reviewed_by, str) or not reviewed_by.strip():
            raise ValueError("reviewed_by is required for taxonomy updates")
        item = TaxonomyValue.model_validate(item.model_dump())
        self.repository.add_taxonomy_value(item)
