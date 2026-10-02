"""One mapping between analysis labels and stored taxonomy values."""

SEVERITY_VALUES = frozenset({"low", "medium", "high", "critical"})
SENTIMENT_VALUES = frozenset({"positive", "neutral", "negative", "frustrated"})


def normalize_severity(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("severity must be text")
    normalized = value.strip().lower()
    if normalized not in SEVERITY_VALUES:
        raise ValueError("unknown severity")
    return normalized


def normalize_sentiment(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("sentiment must be text")
    normalized = value.strip().lower()
    if normalized == "angry":
        normalized = "negative"
    if normalized not in SENTIMENT_VALUES:
        raise ValueError("unknown sentiment")
    return normalized
