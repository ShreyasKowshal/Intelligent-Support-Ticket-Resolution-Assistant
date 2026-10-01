"""Google Gemini adapter for the provider-independent LLM interface."""

import os
from typing import Literal

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .config import get_gemini_model


class MissingApiKeyError(RuntimeError):
    """Gemini credentials were not supplied."""


class GeminiTimeoutError(RuntimeError):
    """The Gemini request exceeded its timeout."""


class GeminiRateLimitError(RuntimeError):
    """Gemini refused the request because of a rate limit."""


class GeminiProviderError(RuntimeError):
    """Gemini could not complete the request."""


class GeminiAnalysisShape(BaseModel):
    """Small wire schema accepted by Gemini; ComplaintAnalysis validates the result."""

    intent: str
    category: str
    product: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    sentiment: Literal["POSITIVE", "NEUTRAL", "FRUSTRATED", "ANGRY"]
    confidence: float
    needs_review: bool
    rationale: str


class GeminiResolutionStepShape(BaseModel):
    step_number: int
    action: str
    source_ids: list[str]


class GeminiResolutionShape(BaseModel):
    """Simple wire schema; rag.py applies stricter validation and citation checks."""

    problem_summary: str
    resolution_steps: list[GeminiResolutionStepShape]
    escalation_recommendation: str
    confidence_or_evidence_note: str
    sources_used: list[str]
    insufficient_evidence: bool


class GeminiClient:
    """The only application component that imports the Gemini SDK."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        if not key or not key.strip() or key.strip() == "PASTE_YOUR_REAL_KEY_HERE":
            raise MissingApiKeyError("GEMINI_API_KEY is missing")
        self.model = model or get_gemini_model()
        self._client = genai.Client(api_key=key.strip(), http_options=types.HttpOptions(timeout=30000))

    def generate_analysis(self, system_instruction: str, complaint: str) -> str:
        return self._generate(system_instruction, complaint, GeminiAnalysisShape, 512)

    def generate_resolution(self, system_instruction: str, evidence_context: str) -> str:
        return self._generate(system_instruction, evidence_context, GeminiResolutionShape, 2048)

    def _generate(
        self, system_instruction: str, content: str, schema: type[BaseModel], max_tokens: int
    ) -> str:
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                    max_output_tokens=max_tokens,
                ),
            )
            if not response.text:
                raise GeminiProviderError("Gemini returned no structured result")
            return response.text
        except errors.APIError as exc:
            if exc.code == 429:
                raise GeminiRateLimitError("Gemini rate limit reached") from None
            if exc.code in (408, 504):
                raise GeminiTimeoutError("Gemini request timed out") from None
            raise GeminiProviderError(f"Gemini request failed (HTTP {exc.code})") from None
        except (httpx.TimeoutException, TimeoutError):
            raise GeminiTimeoutError("Gemini request timed out") from None
        except GeminiProviderError:
            raise
        except Exception:
            # SDK exceptions may include request data; never expose their messages.
            raise GeminiProviderError("Gemini request failed") from None

    def close(self) -> None:
        self._client.close()
