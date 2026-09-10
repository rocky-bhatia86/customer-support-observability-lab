"""Single choke point for all LLM calls.

Every agent must call `call_llm` rather than instantiating its own OpenAI
client. This keeps one seam in the codebase for observability: every call
becomes a Langfuse "generation" observation nested under whichever agent
span is currently active (agents each open their own span via @observe).
"""
from __future__ import annotations

from dataclasses import dataclass

from langfuse import get_client, observe
from openai import OpenAI

from support_ai.config import Config


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str


@observe(as_type="generation", name="llm_call", capture_input=False, capture_output=False)
def call_llm(
    config: Config,
    messages: list[dict],
    temperature: float | None = None,
    version: str | None = None,
    prompt=None,
) -> LLMResult:
    """`version` tags the observation with the caller's own prompt/config
    version (e.g. QualityCheckerAgent passes CHECKER_PROMPT_VERSION), so
    traces can be filtered/grouped by it later. `prompt` is an optional
    Langfuse TextPromptClient/ChatPromptClient (from langfuse.get_prompt) --
    passing it links this generation to that managed prompt version in the
    Langfuse UI."""
    resolved_temperature = config.temperature if temperature is None else temperature

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    response = client.chat.completions.create(
        model=config.model_name,
        messages=messages,
        temperature=resolved_temperature,
    )
    choice = response.choices[0].message.content or ""
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    # Real token counts from the OpenAI response only -- never fabricated.
    # Langfuse computes cost server-side from these counts + the model name,
    # provided the model is registered with pricing in the Langfuse project
    # (see README "Cost tracking").
    get_client().update_current_generation(
        model=config.model_name,
        model_parameters={"temperature": resolved_temperature},
        input=messages,
        output=choice,
        usage_details={
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        },
        version=version,
        prompt=prompt,
    )

    return LLMResult(
        text=choice.strip(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=config.model_name,
    )
