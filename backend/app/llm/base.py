"""Abstract LLM client interface.

All provider implementations (OpenAI, Anthropic, etc.) must implement this ABC.
The contract is: accept a system prompt + user content, return raw JSON string.
Validation against pydantic is done by the caller (extraction service).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LlmToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LlmAssistantMessage:
    content: str | None
    tool_calls: list[LlmToolCall] = field(default_factory=list)


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

    def chat_with_messages(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format_json: bool = False,
    ) -> LlmAssistantMessage:
        """Multi-turn chat; optional tools. Override in providers that support tool use."""
        raise NotImplementedError(f"{self.provider_name} does not support chat_with_messages")

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        ...
