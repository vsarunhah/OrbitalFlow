"""OpenAI-compatible LLM client.

Uses the openai SDK with response_format={"type": "json_object"} to force
the model to return valid JSON. The caller is responsible for validating
the JSON against the pydantic schema.

API key is passed at construction time — never stored beyond the instance.
"""

from __future__ import annotations

import logging

import openai

from app.llm.base import LlmAssistantMessage, LlmClient, LlmResponse, LlmToolCall

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIClient(LlmClient):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LlmResponse:
        logger.debug(
            "OpenAI request model=%s tokens_limit=%d",
            self._model,
            max_tokens,
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        choice = response.choices[0]
        usage = response.usage

        return LlmResponse(
            raw_text=choice.message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            model=response.model,
        )

    def chat_with_messages(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format_json: bool = False,
    ) -> LlmAssistantMessage:
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format_json:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        tool_calls: list[LlmToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    LlmToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments or "{}",
                    )
                )
        return LlmAssistantMessage(content=msg.content, tool_calls=tool_calls)
