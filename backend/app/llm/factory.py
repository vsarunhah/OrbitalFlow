"""Factory for constructing an LlmClient from a provider name + API key."""

from __future__ import annotations

from app.llm.base import LlmClient


_REGISTRY: dict[str, type] = {}


def _ensure_registry() -> None:
    if _REGISTRY:
        return
    from app.llm.openai_client import OpenAIClient
    _REGISTRY["openai"] = OpenAIClient


def get_llm_client(provider: str, api_key: str) -> LlmClient:
    _ensure_registry()
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"Unsupported LLM provider: {provider!r}")
    return cls(api_key=api_key)
