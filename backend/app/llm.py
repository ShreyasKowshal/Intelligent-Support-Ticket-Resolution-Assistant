"""Provider-independent interface for structured complaint analysis."""

from typing import Any, Mapping, Protocol

class LLMClient(Protocol):
    def generate_analysis(
        self, system_instruction: str, complaint: str
    ) -> str | Mapping[str, Any]:
        """Return JSON text or a mapping matching the requested schema."""


class FakeLLMClient:
    """Deterministic client for tests and local examples; makes no network calls."""

    def __init__(self, result: str | Mapping[str, Any] | Exception) -> None:
        self.result = result

    def generate_analysis(
        self, system_instruction: str, complaint: str
    ) -> str | Mapping[str, Any]:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
