"""Small, explicit request and response contracts for the HTTP API."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.analysis import ComplaintAnalysis
from app.config import MAX_COMPLAINT_LENGTH
from app.rag import RAGResolution


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComplaintRequest(ApiModel):
    complaint: str = Field(min_length=1, max_length=MAX_COMPLAINT_LENGTH)

    @field_validator("complaint")
    @classmethod
    def nonblank_complaint(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("complaint cannot be blank")
        return value


class SearchRequest(ComplaintRequest):
    top_k_tickets: int | None = Field(default=None, ge=1, le=20, strict=True)
    top_k_kb: int | None = Field(default=None, ge=1, le=20, strict=True)


class TicketMatchResponse(ApiModel):
    source_id: str
    complaint: str
    product: str
    category: str
    resolution: str
    similarity_score: float


class KBMatchResponse(ApiModel):
    source_id: str
    title: str
    content: str
    category: str
    similarity_score: float


class AnalyzeResponse(ApiModel):
    analysis: ComplaintAnalysis
    latency_ms: float = Field(ge=0)


class SearchResponse(ApiModel):
    tickets: list[TicketMatchResponse]
    kb_articles: list[KBMatchResponse]
    latency_ms: float = Field(ge=0)


class ResolveResponse(ApiModel):
    analysis: ComplaintAnalysis
    tickets: list[TicketMatchResponse]
    kb_articles: list[KBMatchResponse]
    resolution: RAGResolution
    source_ids: list[str]
    insufficient_evidence: bool
    non_actionable: bool = False
    latency_ms: float = Field(ge=0)


class ReadyResponse(ApiModel):
    status: str
    database: bool
    search_index: bool
    embedding_model: bool
    gemini_configured: bool


class HealthResponse(ApiModel):
    status: str


class ErrorDetail(ApiModel):
    code: str
    message: str
    fields: list[str] | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail


class UpdateResponse(ApiModel):
    change: str
    index_refreshed: bool


class TaxonomyUpdateRequest(ApiModel):
    kind: str
    value: str
    reviewed_by: str = Field(min_length=1, max_length=100)

    @field_validator("reviewed_by")
    @classmethod
    def nonblank_reviewer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reviewed_by cannot be blank")
        return value


class TaxonomyUpdateResponse(ApiModel):
    status: str
