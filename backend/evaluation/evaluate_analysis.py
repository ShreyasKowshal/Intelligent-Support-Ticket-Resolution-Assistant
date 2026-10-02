"""Score a label-blind deterministic provider through the real analysis service.

The nearest-ticket fake is a reproducible surrogate, not a Gemini quality test.
It sees only indexed approved ticket text and never the evaluation labels.
"""

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import precision_recall_fscore_support
from sklearn.metrics.pairwise import cosine_similarity

from app.analysis import ComplaintAnalyzer
from app.llm import FakeLLMClient
from app.storage import Repository
from evaluation.fixtures import analysis_cases
from evaluation.metrics import classification_metrics

FIELDS = ("category", "product", "severity", "sentiment", "intent")
INTENTS = {
    "broadband_connectivity": "restore_service",
    "slow_internet": "restore_speed",
    "router_issue": "repair_equipment",
    "billing_dispute": "explain_charge",
    "payment_issue": "trace_payment",
    "sim_activation": "activate_sim",
    "mobile_network": "restore_calls",
    "mobile_data": "restore_mobile_data",
    "roaming": "restore_roaming",
    "recharge_failure": "trace_recharge",
    "account_access": "recover_account",
    "service_outage": "check_outage",
}
SENTIMENTS = {
    "positive": "POSITIVE", "neutral": "NEUTRAL",
    "frustrated": "FRUSTRATED", "negative": "ANGRY",
}


class NearestTicketFakeProvider:
    """A fixed lexical surrogate; no query ID or reference label is supplied."""

    def __init__(self, repository: Repository) -> None:
        self.tickets = repository.list_tickets(evidence_only=True)
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform([item.complaint for item in self.tickets])

    def generate_analysis(self, _instruction: str, complaint: str) -> dict:
        query = self.vectorizer.transform([complaint])
        index = int(np.argmax(cosine_similarity(query, self.matrix).ravel()))
        ticket = self.tickets[index]
        return {
            "intent": INTENTS[ticket.category],
            "category": ticket.category,
            "product": ticket.product,
            "severity": ticket.severity.upper(),
            "sentiment": SENTIMENTS[ticket.sentiment],
            "confidence": 0.7,
            "needs_review": False,
            "rationale": "Deterministic nearest-ticket surrogate output.",
        }


def evaluate(repository: Repository) -> dict:
    cases = analysis_cases()
    provider = NearestTicketFakeProvider(repository)
    analyzer = ComplaintAnalyzer.from_repository(provider, repository)
    expected = {field: [] for field in FIELDS}
    predicted = {field: [] for field in FIELDS}
    review_expected = []
    review_predicted = []
    for case in cases:
        analysis = analyzer.analyze(case["complaint"])
        for field in FIELDS:
            expected[field].append(case[f"expected_{field}"])
            value = getattr(analysis, field)
            predicted[field].append(value.value if hasattr(value, "value") else value)
        review_expected.append(str(case["expected_needs_review"]))
        review_predicted.append(str(analysis.needs_review))

    # Separately exercise normalization when a provider proposes a new class.
    # This is a contract check, not part of the surrogate model scores.
    novel = next(case for case in cases if "raw_category" in case)
    raw = provider.generate_analysis("", novel["complaint"])
    raw["category"] = novel["raw_category"]
    normalized = ComplaintAnalyzer.from_repository(FakeLLMClient(raw), repository).analyze(
        novel["complaint"]
    )
    unknown_passed = (
        normalized.category == "other" and normalized.needs_review
        and normalized.suggested_category == novel["raw_category"]
    )
    review_precision, review_recall, review_f1, _ = precision_recall_fscore_support(
        review_expected, review_predicted, average="binary", pos_label="True", zero_division=0,
    )
    return {
        "mode": "label_blind_nearest_ticket_fake_provider",
        "provider_receives_reference_labels": False,
        "samples": len(cases),
        "fields": {
            field: classification_metrics(expected[field], predicted[field])
            for field in FIELDS
        },
        "needs_review": classification_metrics(review_expected, review_predicted),
        "needs_review_positive": {
            "precision": round(float(review_precision), 4),
            "recall": round(float(review_recall), 4),
            "f1": round(float(review_f1), 4),
        },
        "unknown_category_checks": 1,
        "unknown_category_passed": unknown_passed,
        "limitation": "A lexical fake provider measures the analysis path, not Gemini model quality.",
    }
