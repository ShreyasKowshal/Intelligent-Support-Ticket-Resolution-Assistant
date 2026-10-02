"""Compare FAISS retrieval with a TF-IDF baseline on identical source text."""

from difflib import SequenceMatcher

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.search import SemanticSearch, kb_embedding_text, ticket_embedding_text
from app.storage import Repository
from evaluation.fixtures import held_out_queries
from evaluation.metrics import ranking_metrics


class TfidfBaseline:
    def __init__(self, ids: list[str], texts: list[str]) -> None:
        if not ids or len(ids) != len(texts):
            raise ValueError("baseline needs aligned source IDs and texts")
        self.ids = ids
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, norm="l2")
        self.matrix = self.vectorizer.fit_transform(texts)

    def rank(self, complaint: str) -> list[str]:
        query = self.vectorizer.transform([complaint])
        scores = cosine_similarity(query, self.matrix).ravel()
        # Stable source-ID tie break makes reruns byte-for-byte reproducible.
        order = sorted(range(len(self.ids)), key=lambda index: (-scores[index], self.ids[index]))
        return [self.ids[index] for index in order]


def _relevant_ids(query: dict, prefix: str) -> set[str]:
    return {source_id for source_id in query["relevant_source_ids"] if source_id.startswith(prefix)}


def evaluate(repository: Repository, search: SemanticSearch) -> dict:
    tickets = repository.list_tickets(evidence_only=True)
    kb_articles = repository.list_kb_articles(evidence_only=True)
    ticket_ids = [ticket.ticket_id for ticket in tickets]
    kb_ids = [article.kb_id for article in kb_articles]
    ticket_baseline = TfidfBaseline(ticket_ids, [ticket_embedding_text(item) for item in tickets])
    kb_baseline = TfidfBaseline(kb_ids, [kb_embedding_text(item) for item in kb_articles])
    indexed_complaints = [ticket.complaint.strip().casefold() for ticket in tickets]
    rankings: dict[str, dict[str, list[tuple[list[str], set[str]]]]] = {
        method: {source_type: [] for source_type in ("tickets", "kb_articles")}
        for method in ("faiss", "tfidf")
    }
    diagnostics = []
    exact_duplicates = []
    near_duplicates = []
    for query in held_out_queries():
        complaint = query["complaint"]
        normalized = complaint.strip().casefold()
        if normalized in indexed_complaints:
            exact_duplicates.append(query["query_id"])
        max_ratio = max(SequenceMatcher(None, normalized, text).ratio() for text in indexed_complaints)
        if max_ratio >= 0.9:
            near_duplicates.append(query["query_id"])
        relevant_tickets = _relevant_ids(query, "T-")
        relevant_kb = _relevant_ids(query, "KB-")
        if not relevant_tickets <= set(ticket_ids) or not relevant_kb <= set(kb_ids):
            raise ValueError(f"query {query['query_id']} names ineligible or missing evidence")
        results = search.search(complaint, ticket_k=len(ticket_ids), kb_k=len(kb_ids))
        faiss_ticket_ids = [item.source_id for item in results.tickets]
        faiss_kb_ids = [item.source_id for item in results.kb_articles]
        tfidf_ticket_ids = ticket_baseline.rank(complaint)
        tfidf_kb_ids = kb_baseline.rank(complaint)
        if relevant_tickets:
            rankings["faiss"]["tickets"].append((faiss_ticket_ids, relevant_tickets))
            rankings["tfidf"]["tickets"].append((tfidf_ticket_ids, relevant_tickets))
        if relevant_kb:
            rankings["faiss"]["kb_articles"].append((faiss_kb_ids, relevant_kb))
            rankings["tfidf"]["kb_articles"].append((tfidf_kb_ids, relevant_kb))
        diagnostics.append({
            "query_id": query["query_id"],
            "relevant_ticket_ids": sorted(relevant_tickets),
            "relevant_kb_ids": sorted(relevant_kb),
            "faiss_ticket_top_5": faiss_ticket_ids[:5],
            "tfidf_ticket_top_5": tfidf_ticket_ids[:5],
            "faiss_kb_top_5": faiss_kb_ids[:5],
            "tfidf_kb_top_5": tfidf_kb_ids[:5],
        })
    if exact_duplicates:
        raise ValueError(f"held-out complaints duplicate indexed ticket text: {exact_duplicates}")
    return {
        "source_counts": {"tickets": len(tickets), "kb_articles": len(kb_articles)},
        "relevance_policy": "Only explicitly labeled source IDs count; unlabeled source types are excluded.",
        "mrr_policy": "Full-ranking reciprocal rank, not truncated at five.",
        "shared_source_text": "ticket_embedding_text and kb_embedding_text",
        "faiss": {kind: ranking_metrics(rankings["faiss"][kind]) for kind in rankings["faiss"]},
        "tfidf": {kind: ranking_metrics(rankings["tfidf"][kind]) for kind in rankings["tfidf"]},
        "leakage_audit": {
            "exact_ticket_complaint_duplicates": exact_duplicates,
            "near_ticket_complaint_matches_ratio_ge_0_9": near_duplicates,
            "ticket_text_excludes_resolution": all(
                ticket.resolution not in ticket_embedding_text(ticket) for ticket in tickets
            ),
            "query_uses_only_complaint": True,
        },
        "per_query": diagnostics,
    }
