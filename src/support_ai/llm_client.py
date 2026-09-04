"""Single choke point for all LLM calls.

Every agent must call `call_llm` rather than instantiating its own OpenAI
client. This keeps one seam in the codebase for the later observability lab
stage to instrument (see LAB_PLAN.md).
"""
from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from support_ai.config import Config


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str


def call_llm(
    config: Config,
    messages: list[dict],
    temperature: float | None = None,
) -> LLMResult:
    client = OpenAI(api_key=config.api_key)
    response = client.chat.completions.create(
        model=config.model_name,
        messages=messages,
        temperature=config.temperature if temperature is None else temperature,
    )
    choice = response.choices[0].message.content or ""
    usage = response.usage
    return LLMResult(
        text=choice.strip(),
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        model=config.model_name,
    )
