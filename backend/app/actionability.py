"""Conservative gate for inputs that cannot support telecom troubleshooting."""

import re

from app.analysis import ComplaintAnalysis


DOMAIN_WORDS = frozenset({
    "account", "bill", "broadband", "call", "calls", "cellular", "connection", "data",
    "fiber", "fibre", "internet", "mobile", "modem", "network", "phone",
    "recharge", "roaming", "router", "service", "signal", "sim", "telecom", "wifi",
})
PROBLEM_WORDS = frozenset({
    "activate", "bad", "billing", "blocked", "broken", "cancel", "cannot",
    "charge", "charged", "disconnect", "disconnected", "down", "drop",
    "dropping", "drops", "error", "fail", "failed", "fails", "failure", "help", "issue",
    "high", "locked", "lost", "missing", "need", "no", "not", "outage", "problem", "refund", "slow", "stopped",
    "unable", "unstable", "weak", "working",
})
KEYWORD_ONLY_WORDS = DOMAIN_WORDS | {"laptop", "tablet"}
CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxyz]{6,}", re.IGNORECASE)
TELECOM_SERVICE_WORDS = frozenset({
    "billing", "broadband", "call", "calls", "cellular", "connection", "data",
    "fiber", "fibre", "internet", "modem", "network", "plan", "recharge",
    "roaming", "router", "signal", "sim", "sms", "telecom", "wifi",
})
SPECIFIC_TELECOM_WORDS = (TELECOM_SERVICE_WORDS - {"connection", "telecom"}) | {
    "account", "bill", "mobile", "phone",
}
TEXT_MESSAGE = re.compile(r"\b(?:text messages?|texts)\b", re.IGNORECASE)
VAGUE_REASON = re.compile(
    r"\b(?:vague|unspecified|unclear|too general|insufficient (?:detail|information)"
    r"|not enough (?:detail|information)|(?:does not|doesn't) specify)\b",
    re.IGNORECASE,
)
LOCAL_DEVICE = frozenset({"computer", "laptop", "pc", "windows"})
LOCAL_ACCESS = frozenset({"login", "logon", "password", "signin"})
LOG_IN = re.compile(r"\blog(?:ging)?\s+in(?:to)?\b", re.IGNORECASE)
TELECOM_ACCOUNT = re.compile(
    r"\b(?:telecom|carrier|(?:mobile|cellular) provider|customer portal)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_REASON = re.compile(
    r"\b(?:non[ -]?telecom|outside (?:telecom|carrier)"
    r"|(?:unrelated|not related) to (?:telecom|network|carrier|service|account)"
    r"|not (?:a |related to )?telecom)\b",
    re.IGNORECASE,
)
DEVICE_REASON = re.compile(r"\b(?:hardware|software|physical damage|device repair)\b", re.IGNORECASE)


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
    has_telecom_service = bool(tokens & TELECOM_SERVICE_WORDS or TEXT_MESSAGE.search(text))
    if (
        analysis.category in {"account_access", "other"}
        and tokens & LOCAL_DEVICE
        and (tokens & LOCAL_ACCESS or LOG_IN.search(text))
        and not has_telecom_service
        and not TELECOM_ACCOUNT.search(text)
    ):
        return True
    if (
        analysis.category == "other"
        and analysis.product == "other"
        and analysis.needs_review
        and analysis.confidence < 0.60
        and analysis.suggested_category is None
        and not (tokens & SPECIFIC_TELECOM_WORDS or TEXT_MESSAGE.search(text))
        and VAGUE_REASON.search(f"{analysis.intent} {analysis.rationale}")
    ):
        return True
    if analysis.category == "other" and analysis.needs_review and not has_telecom_service:
        reasoning = f"{analysis.intent} {analysis.rationale}"
        if OUT_OF_SCOPE_REASON.search(reasoning) or DEVICE_REASON.search(reasoning):
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
