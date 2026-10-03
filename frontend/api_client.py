"""The frontend's only connection to the support-assistant backend."""

import logging
import os
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from backend.app.config import MAX_COMPLAINT_LENGTH

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0)
READINESS_TIMEOUT = httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0)
WAKE_CONNECT_TIMEOUT_SECONDS = 5.0
WAKE_READ_TIMEOUT_SECONDS = 115.0
ReadinessState = Literal["ready", "starting", "unavailable"]
HealthState = Literal["alive", "starting", "unavailable"]
wake_logger = logging.getLogger("frontend.wake")


class FrontendError(Exception):
    """A short, safe message suitable for the agent-facing page."""


class BackendConnectionError(FrontendError):
    """The backend connection failed after the UI had been ready."""


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
    non_actionable: bool = False
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
            if self.non_actionable and (self.tickets or self.kb_articles):
                raise ValueError("non-actionable input must not contain retrieved evidence")
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
    configured = os.getenv("API_BASE_URL", "").strip()
    hosted = os.getenv("RENDER") == "true"
    if hosted and not configured:
        raise FrontendError("The backend address is not configured. Check API_BASE_URL.")
    raw = configured or DEFAULT_API_BASE_URL
    try:
        url = httpx.URL(raw)
    except (TypeError, ValueError):
        raise FrontendError("The backend address is invalid. Check API_BASE_URL.") from None
    if (
        url.scheme not in ("http", "https") or not url.host or url.userinfo
        or url.query or url.fragment or url.path not in ("", "/")
        or (hosted and (url.scheme != "https" or url.host in ("localhost", "127.0.0.1", "::1") or url.port))
    ):
        raise FrontendError("The backend address is invalid. Check API_BASE_URL.")
    return str(url).rstrip("/")


def check_backend_health(
    *, transport: httpx.BaseTransport | None = None,
    read_timeout: float = WAKE_READ_TIMEOUT_SECONDS,
) -> HealthState:
    """Wake a sleeping backend with its lightweight liveness route."""
    try:
        base_url = get_api_base_url()
    except FrontendError:
        wake_logger.error("FRONTEND_WAKE_CONFIG_ERROR")
        return "unavailable"
    wake_logger.warning("FRONTEND_WAKE_TARGET=%s", httpx.URL(base_url).host)
    url = base_url + "/health"
    try:
        timeout = httpx.Timeout(
            connect=WAKE_CONNECT_TIMEOUT_SECONDS, read=read_timeout,
            write=5.0, pool=5.0,
        )
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=False) as client:
            wake_logger.warning("FRONTEND_WAKE_REQUEST_START")
            response = client.get(url)
    except httpx.TimeoutException as exc:
        wake_logger.warning("FRONTEND_WAKE_REQUEST_TIMEOUT type=%s", type(exc).__name__)
        return "starting"
    except httpx.RequestError as exc:
        wake_logger.warning("FRONTEND_WAKE_REQUEST_EXCEPTION=%s", type(exc).__name__)
        return "starting"
    except Exception as exc:
        wake_logger.error("FRONTEND_WAKE_REQUEST_EXCEPTION=%s", type(exc).__name__)
        return "unavailable"
    wake_logger.warning("FRONTEND_WAKE_REQUEST_STATUS=%d", response.status_code)
    if response.status_code in (401, 403, 404, 405):
        return "unavailable"
    if response.status_code != 200:
        return "starting"
    try:
        if response.json().get("status") == "ok":
            return "alive"
        return "starting"
    except (ValueError, AttributeError):
        return "starting"


def check_backend_readiness(*, transport: httpx.BaseTransport | None = None) -> ReadinessState:
    """Check processing dependencies only after /health confirms liveness."""
    try:
        url = get_api_base_url() + "/ready"
    except FrontendError:
        return "unavailable"
    try:
        with httpx.Client(timeout=READINESS_TIMEOUT, transport=transport, follow_redirects=False) as client:
            response = client.get(url)
    except (httpx.TimeoutException, httpx.RequestError):
        return "starting"
    if response.status_code in (401, 403, 404, 405):
        return "unavailable"
    if response.status_code not in (200, 503):
        return "starting"
    try:
        details = response.json()
        if not isinstance(details, dict):
            return "starting"
        if details.get("gemini_configured") is False:
            return "unavailable"
        if response.status_code == 200:
            return "ready" if (
                details.get("status") == "ready"
                and all(details.get(field) is True for field in (
                    "database", "search_index", "embedding_model", "gemini_configured"
                ))
            ) else "starting"
        return "starting"
    except ValueError:
        return "starting"


def resolve_complaint(
    complaint: str, *, transport: httpx.BaseTransport | None = None,
) -> ResolveResult:
    """Submit one complaint to FastAPI; never call Gemini from this process."""
    if not isinstance(complaint, str) or not complaint.strip():
        raise FrontendError("Enter a customer complaint before continuing.")
    if len(complaint) > MAX_COMPLAINT_LENGTH:
        raise FrontendError(f"Complaint must be {MAX_COMPLAINT_LENGTH} characters or fewer.")
    complaint = complaint.strip()
    url = get_api_base_url() + "/resolve"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, transport=transport, follow_redirects=False) as client:
            response = client.post(url, json={"complaint": complaint})
    except httpx.TimeoutException:
        raise FrontendError("The analysis request timed out. Please try again.") from None
    except httpx.RequestError:
        raise BackendConnectionError(
            "Backend is starting. Please wait until the status changes to Ready."
        ) from None

    if response.status_code != 200:
        try:
            error_code = response.json().get("error", {}).get("code")
        except (ValueError, AttributeError, TypeError):
            error_code = None
        raise FrontendError(ERROR_MESSAGES.get(
            error_code,
            "The backend returned an unexpected error. Please try again or check service status.",
        ))
    try:
        return ResolveResult.model_validate(response.json())
    except (ValueError, ValidationError, TypeError):
        raise FrontendError("The backend returned an invalid response. Please try again.") from None
