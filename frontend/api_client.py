"""The frontend's only connection to the support-assistant backend."""

import os

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
MAX_COMPLAINT_LENGTH = 4000
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0)


class FrontendError(Exception):
    """A short, safe message suitable for the agent-facing page."""


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Analysis(ApiModel):
    intent: str
    category: str
    product: str
    severity: str
    sentiment: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    needs_review: bool
    rationale: str
    suggested_category: str | None = None


class Ticket(ApiModel):
    source_id: str
    complaint: str
    product: str
    category: str
    resolution: str
    similarity_score: float = Field(ge=-1, le=1, allow_inf_nan=False)


class KBArticle(ApiModel):
    source_id: str
    title: str
    content: str
    category: str
    similarity_score: float = Field(ge=-1, le=1, allow_inf_nan=False)


class ResolutionStep(ApiModel):
    step_number: int = Field(ge=1)
    action: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class Resolution(ApiModel):
    problem_summary: str
    resolution_steps: list[ResolutionStep]
    escalation_recommendation: str
    confidence_or_evidence_note: str
    sources_used: list[str]
    insufficient_evidence: bool


class ResolveResult(ApiModel):
    analysis: Analysis
    tickets: list[Ticket]
    kb_articles: list[KBArticle]
    resolution: Resolution
    source_ids: list[str]
    insufficient_evidence: bool
    latency_ms: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_response_consistency(self) -> "ResolveResult":
        if (
            self.source_ids != self.resolution.sources_used
            or self.insufficient_evidence != self.resolution.insufficient_evidence
        ):
            raise ValueError("response fields disagree")
        if self.insufficient_evidence:
            if self.resolution.resolution_steps or self.source_ids:
                raise ValueError("insufficient evidence must not contain a recommendation")
        elif not self.resolution.resolution_steps:
            raise ValueError("recommendation has no cited steps")
        elif any(
            not set(step.source_ids) <= set(self.source_ids)
            for step in self.resolution.resolution_steps
        ):
            raise ValueError("cited steps disagree with the source list")
        return self


ERROR_MESSAGES = {
    "validation_error": "Please check the complaint and try again.",
    "missing_configuration": "The AI service is not configured. Ask an administrator to check the backend.",
    "provider_error": "The AI provider is unavailable right now. Please try again later.",
    "provider_timeout": "The AI provider timed out. Please try again later.",
    "provider_rate_limit": "The AI provider is busy. Please try again later.",
    "invalid_analysis": "The AI analysis could not be validated. Please try again.",
    "grounding_error": "The draft failed citation checks. No recommendation was shown.",
    "search_unavailable": "Semantic search is unavailable right now. Please try again later.",
    "storage_unavailable": "The support database is unavailable right now.",
}


def get_api_base_url() -> str:
    """Read a local default or an explicit API origin without exposing it in the UI."""
    raw = (os.getenv("API_BASE_URL") or DEFAULT_API_BASE_URL).strip()
    try:
        url = httpx.URL(raw)
    except (TypeError, ValueError):
        raise FrontendError("The backend address is invalid. Check API_BASE_URL.") from None
    if url.scheme not in ("http", "https") or not url.host or url.userinfo or url.query or url.fragment:
        raise FrontendError("The backend address is invalid. Check API_BASE_URL.")
    return str(url).rstrip("/")


def resolve_complaint(
    complaint: str, *, transport: httpx.BaseTransport | None = None,
) -> ResolveResult:
    """Submit one complaint to FastAPI; never call Gemini from this process."""
    if not isinstance(complaint, str) or not complaint.strip():
        raise FrontendError("Enter a customer complaint before continuing.")
    complaint = complaint.strip()
    if len(complaint) > MAX_COMPLAINT_LENGTH:
        raise FrontendError(f"Keep the complaint under {MAX_COMPLAINT_LENGTH} characters.")
    url = get_api_base_url() + "/resolve"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, transport=transport, follow_redirects=False) as client:
            response = client.post(url, json={"complaint": complaint})
    except httpx.TimeoutException:
        raise FrontendError("The request timed out. Check the backend and try again.") from None
    except httpx.RequestError:
        raise FrontendError("The backend cannot be reached. Check that FastAPI is running.") from None

    if response.status_code != 200:
        try:
            error_code = response.json().get("error", {}).get("code")
        except (ValueError, AttributeError, TypeError):
            error_code = None
        raise FrontendError(ERROR_MESSAGES.get(error_code, "The request could not be completed. Please try again."))
    try:
        return ResolveResult.model_validate(response.json())
    except (ValueError, ValidationError, TypeError):
        raise FrontendError("The backend returned an invalid response. Please try again.") from None
