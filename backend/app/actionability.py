"""Conservative gate for inputs that cannot support telecom troubleshooting."""

import re

from app.analysis import ComplaintAnalysis


DOMAIN_WORDS = frozenset({
    "account", "broadband", "call", "calls", "cellular", "connection", "data",
    "fiber", "fibre", "internet", "mobile", "modem", "network", "phone",
    "recharge", "router", "service", "signal", "sim", "telecom", "wifi",
})
PROBLEM_WORDS = frozenset({
    "activate", "bad", "billing", "blocked", "broken", "cancel", "cannot",
    "charge", "charged", "disconnect", "disconnected", "down", "drop",
    "drops", "error", "fail", "failed", "fails", "failure", "help", "issue",
    "lost", "need", "not", "outage", "problem", "refund", "slow", "stopped",
    "unable", "unstable", "weak", "working",
})
KEYWORD_ONLY_WORDS = DOMAIN_WORDS | {"laptop", "tablet"}
CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxyz]{6,}", re.IGNORECASE)


def is_non_actionable_complaint(complaint: str, analysis: ComplaintAnalysis) -> bool:
    """Reject obvious noise, then use analysis plus complaint signals conservatively.

    A weak confidence or needs_review flag alone never suppresses retrieval.
    """
    text = complaint.strip()
    words = re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
    if not words or (len(words) == 1 and len(words[0]) == 1):
        return True
    if re.fullmatch(r"https?://\S+", text, re.IGNORECASE):
        return True
    if len(words) >= 3 and len(set(words)) == 1:
        return True
    if len(words) == 1 and words[0].isascii():
        if len(set(words[0])) == 1 or CONSONANT_RUN.search(words[0]):
            return True

    tokens = set(words)
    if len(words) >= 2 and tokens <= KEYWORD_ONLY_WORDS:
        return True
    describes_telecom_problem = bool(tokens & DOMAIN_WORDS and tokens & PROBLEM_WORDS)
    if describes_telecom_problem:
        return False
    return (
        analysis.category == "other"
        and analysis.product == "other"
        and analysis.needs_review
        and analysis.suggested_category is None
    )
