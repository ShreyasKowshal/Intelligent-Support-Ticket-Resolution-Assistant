"""Small environment-based settings for the API."""

import os


def get_app_title() -> str:
    """Return the API title, with a useful local default."""
    return os.getenv("APP_TITLE") or "Support Ticket Resolution Assistant"
