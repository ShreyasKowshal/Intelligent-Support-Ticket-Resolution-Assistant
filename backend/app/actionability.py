"""Conservative gate for inputs that cannot support telecom troubleshooting."""

import re
from typing import Literal

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
LOCAL_DEVICE = frozenset({"computer", "desktop", "laptop", "mac", "macos", "pc", "windows"})
LOCAL_ACCESS = frozenset({"login", "logon", "password", "pin", "profile", "signin"})
LOG_IN = re.compile(r"\b(?:log|sign)(?:ging|ing)?\s+in(?:to)?\b", re.IGNORECASE)
LOCAL_ACCOUNT_LOCK = re.compile(r"\b(?:account|profile)\s+(?:is\s+)?locked\b", re.IGNORECASE)
TELECOM_ACCOUNT = re.compile(
    r"\b(?:telecom|carrier|(?:mobile|cellular|broadband) provider|customer portal)\b",
    re.IGNORECASE,
)
THIRD_PARTY_ACCOUNT = re.compile(
    r"\b(?:google|gmail|microsoft|outlook|facebook|instagram|apple id|icloud"
    r"|yahoo|amazon|netflix)\b",
)
ACCOUNT_ACCESS = re.compile(
    r"\b(?:password|passcode|passphrase|pin|login|logon|signin|locked|forgot"
    r"|reset|recover|recovery)\b|\b(?:log|sign) in(?:to)?\b",
)
OTHER_TELECOM_ISSUE = re.compile(
    r"\b(?:mobile data|broadband|cellular|carrier|telecom|customer portal|sim"
    r"|signal|calls?|roaming|recharge|router|modem)\b",
)
WIFI_PASSWORD = re.compile(r"\bwifi\b.*\b(?:password|passcode|passphrase)\b|\b(?:password|passcode|passphrase)\b.*\bwifi\b")
ROUTER_PASSWORD = re.compile(r"\b(?:router|modem)\b")
ClarificationKind = Literal["third_party_account", "wifi_password", "router_wifi_password"]
OUT_OF_SCOPE_REASON = re.compile(
    r"\b(?:non[ -]?telecom|outside (?:telecom|carrier)"
    r"|(?:unrelated|not related) to (?:telecom|network|carrier|service|account)"
    r"|not (?:a |related to )?telecom)\b",
    re.IGNORECASE,
)
DEVICE_REASON = re.compile(r"\b(?:hardware|software|physical damage|device repair)\b", re.IGNORECASE)
NO_INCIDENT_REASON = re.compile(
    r"\b(?:educational|informational|general knowledge|casual|observation"
    r"|no (?:telecom |service |customer )?(?:issue|problem|fault|complaint)"
    r"|not (?:a |an )?(?:complaint|service issue|support incident)"
    r"|not (?:reporting|describing) (?:a |an )?(?:telecom |service )?(?:issue|problem|fault))\b",
    re.IGNORECASE,
)


def normalize_for_checks(complaint: str) -> str:
    """Keep words and numbers while ignoring decorative symbols in deterministic checks."""
    words = re.findall(r"[^\W_]+", complaint.casefold(), flags=re.UNICODE)
    return re.sub(r"\bwi fi\b", "wifi", " ".join(words))


def clarification_kind(complaint: str) -> ClarificationKind | None:
    """Catch narrow account-scope ambiguity before telecom retrieval or drafting."""
    text = normalize_for_checks(complaint)
    if THIRD_PARTY_ACCOUNT.search(text) and ACCOUNT_ACCESS.search(text):
        if not TELECOM_ACCOUNT.search(text) and not OTHER_TELECOM_ISSUE.search(text):
            return "third_party_account"
    if WIFI_PASSWORD.search(text):
        if TELECOM_ACCOUNT.search(text):
            return None
        if ROUTER_PASSWORD.search(text):
            return "router_wifi_password"
        return "wifi_password"
    return None


def is_non_actionable_complaint(complaint: str, analysis: ComplaintAnalysis) -> bool:
    """Reject obvious noise, then use analysis plus complaint signals conservatively.

    A weak confidence or needs_review flag alone never suppresses retrieval.
    """
    text = normalize_for_checks(complaint)
    words = re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
    if not words or (len(words) == 1 and len(words[0]) == 1):
        return True
    if re.fullmatch(r"https?://\S+", complaint.strip(), re.IGNORECASE):
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
    describes_telecom_problem = bool(tokens & DOMAIN_WORDS and tokens & PROBLEM_WORDS)
    if (
        tokens & LOCAL_DEVICE
        and (tokens & LOCAL_ACCESS or LOG_IN.search(text) or LOCAL_ACCOUNT_LOCK.search(text))
        and not has_telecom_service
        and not TELECOM_ACCOUNT.search(text)
    ):
        return True
    reasoning = f"{analysis.intent} {analysis.rationale}"
    if not describes_telecom_problem and NO_INCIDENT_REASON.search(reasoning):
        return True
    if (
        analysis.category == "other"
        and analysis.product == "other"
        and analysis.needs_review
        and analysis.confidence < 0.60
        and analysis.suggested_category is None
        and not (tokens & SPECIFIC_TELECOM_WORDS or TEXT_MESSAGE.search(text))
        and VAGUE_REASON.search(reasoning)
    ):
        return True
    if analysis.category == "other" and analysis.needs_review and not has_telecom_service:
        if OUT_OF_SCOPE_REASON.search(reasoning) or DEVICE_REASON.search(reasoning):
            return True
    if describes_telecom_problem:
        return False
    return (
        analysis.category == "other"
        and analysis.product == "other"
        and analysis.needs_review
        and analysis.suggested_category is None
    )
