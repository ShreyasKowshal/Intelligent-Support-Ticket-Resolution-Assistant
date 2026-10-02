"""Validated records used by the storage layer and seed data."""

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.taxonomy import normalize_sentiment, normalize_severity

Severity = Literal["low", "medium", "high", "critical"]
Sentiment = Literal["positive", "neutral", "negative", "frustrated"]
TicketStatus = Literal["open", "resolved"]
TaxonomyKind = Literal["product", "category", "severity", "sentiment"]
SourceType = Literal["ticket", "kb"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupportTicket(Record):
    ticket_id: str = Field(max_length=32, pattern=r"^T-\d{3,}$")
    complaint: str = Field(min_length=1)
    product: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    severity: Severity
    sentiment: Sentiment
    resolution: str
    status: TicketStatus
    approved: StrictBool
    created_at: datetime
    updated_at: datetime

    @field_validator("severity", mode="before")
    @classmethod
    def canonical_severity(cls, value: str) -> str:
        return normalize_severity(value)

    @field_validator("sentiment", mode="before")
    @classmethod
    def canonical_sentiment(cls, value: str) -> str:
        return normalize_sentiment(value)

    @field_validator("complaint", "product", "category", "resolution")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_state(self) -> "SupportTicket":
        if not self.complaint or not self.product or not self.category:
            raise ValueError("complaint, product, and category cannot be blank")
        if self.status == "resolved" and not self.resolution:
            raise ValueError("resolved tickets require a resolution")
        if self.status == "open" and self.approved:
            raise ValueError("open tickets cannot be approved")
        _check_timestamps(self.created_at, self.updated_at)
        return self


class KnowledgeBaseArticle(Record):
    kb_id: str = Field(max_length=32, pattern=r"^KB-\d{3,}$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=80)
    approved: StrictBool
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("title", "content", "category")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_content(self) -> "KnowledgeBaseArticle":
        if not self.title or not self.content or not self.category:
            raise ValueError("title, content, and category cannot be blank")
        _check_timestamps(self.created_at, self.updated_at)
        return self


class TaxonomyValue(Record):
    kind: TaxonomyKind
    value: str = Field(min_length=1, max_length=80)

    @field_validator("value")
    @classmethod
    def strip_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("taxonomy value cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_value(self) -> "TaxonomyValue":
        if self.kind == "severity":
            self.value = normalize_severity(self.value)
        elif self.kind == "sentiment":
            self.value = normalize_sentiment(self.value)
        elif not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", self.value):
            raise ValueError("product and category values must be lowercase identifiers")
        return self


class EmbeddingMetadata(Record):
    source_id: str = Field(min_length=1)
    source_type: SourceType
    model_name: str = Field(min_length=1, max_length=120)
    model_version: str = Field(min_length=1, max_length=80)
    vector_bytes: bytes | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_source_id(self) -> "EmbeddingMetadata":
        prefix = "T-" if self.source_type == "ticket" else "KB-"
        if not self.source_id.startswith(prefix):
            raise ValueError("source_id does not match source_type")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must include a timezone")
        return self


def _check_timestamps(created_at: datetime, updated_at: datetime) -> None:
    if created_at.tzinfo is None or updated_at.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    if updated_at < created_at:
        raise ValueError("updated_at cannot precede created_at")
