"""Provider-independent interface for structured complaint analysis."""

from typing import Any, Mapping, Protocol

class LLMClient(Protocol):
    def generate_analysis(
        self, system_instruction: str, complaint: str
    ) -> str | Mapping[str, Any]:
        """Return JSON text or a mapping matching the requested schema."""

    def generate_resolution(
        self, system_instruction: str, evidence_context: str
    ) -> str | Mapping[str, Any]:
        """Return a structured resolution grounded in the supplied context."""


class FakeLLMClient:
    """Deterministic client for tests and local examples; makes no network calls."""

    def __init__(
        self,
        result: str | Mapping[str, Any] | Exception,
        resolution_result: str | Mapping[str, Any] | Exception | None = None,
    ) -> None:
        self.result = result
        self.resolution_result = resolution_result

    def generate_analysis(
        self, system_instruction: str, complaint: str
    ) -> str | Mapping[str, Any]:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def generate_resolution(
        self, system_instruction: str, evidence_context: str
    ) -> str | Mapping[str, Any]:
        if self.resolution_result is None:
            raise RuntimeError("Fake resolution result is not configured")
        if isinstance(self.resolution_result, Exception):
            raise self.resolution_result
        return self.resolution_result
