"""FastAPI entry point."""

from fastapi import FastAPI

from app.config import get_app_title

app = FastAPI(title=get_app_title())


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
