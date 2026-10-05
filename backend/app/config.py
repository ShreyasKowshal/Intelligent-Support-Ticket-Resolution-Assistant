"""Small environment-based settings for the API."""

import os

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_REPO = "qdrant/all-MiniLM-L6-v2-onnx"
EMBEDDING_MODEL_REVISION = "d13954661f83248295ba75c1ed411eef3b7b936e"
EMBEDDING_RUNTIME_VERSION = "fastembed-onnx-v1"
EMBEDDING_TEXT_VERSION = "v1"
DEFAULT_TICKET_TOP_K = 5
DEFAULT_KB_TOP_K = 5
MAX_COMPLAINT_LENGTH = 3000
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


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


def get_gemini_model() -> str:
    """Allow a model change without changing provider code."""
    return os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL


def get_cors_origins() -> list[str]:
    """Allow only explicitly named frontend origins."""
    configured = os.getenv("CORS_ORIGINS")
    if not configured:
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    origins = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    if any(origin == "*" or not origin.startswith(("http://", "https://")) for origin in origins):
        raise ValueError("CORS_ORIGINS must contain explicit HTTP origins")
    return origins
