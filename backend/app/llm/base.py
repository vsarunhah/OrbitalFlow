"""Abstract LLM client interface.

All provider implementations (OpenAI, Anthropic, etc.) must implement this ABC.
The contract is: accept a system prompt + user content, return raw JSON string.
Validation against pydantic is done by the caller (extraction service).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class LlmResponse:
    raw_text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model: str | None = None


class LlmClient(abc.ABC):
    """Provider-agnostic LLM interface."""

    @abc.abstractmethod
    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LlmResponse:
        """Send a chat request expecting a JSON-only response."""
        ...

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        ...
