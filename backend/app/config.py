"""Small environment-based settings for the API."""

import os

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
EMBEDDING_TEXT_VERSION = "v1"
DEFAULT_TICKET_TOP_K = 5
DEFAULT_KB_TOP_K = 5


def get_app_title() -> str:
    """Return the API title, with a useful local default."""
    return os.getenv("APP_TITLE") or "Support Ticket Resolution Assistant"


def get_search_top_k() -> tuple[int, int]:
    """Read optional local search limits with clear validation."""
    try:
        ticket_k = int(os.getenv("SEARCH_TICKET_TOP_K") or DEFAULT_TICKET_TOP_K)
        kb_k = int(os.getenv("SEARCH_KB_TOP_K") or DEFAULT_KB_TOP_K)
    except ValueError as exc:
        raise ValueError("Search Top-K environment values must be positive integers") from exc
    if ticket_k < 1 or kb_k < 1:
        raise ValueError("Search Top-K environment values must be positive integers")
    return ticket_k, kb_k
