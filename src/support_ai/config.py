import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    api_key: str
    model_name: str
    temperature: float
    max_agent_iterations: int
    checker_prompt_version: str
    base_url: str | None = None


def load_config() -> Config:
    return Config(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model_name=os.getenv("MODEL_NAME", "gpt-4o-mini"),
        temperature=float(os.getenv("TEMPERATURE", "0.2")),
        max_agent_iterations=int(os.getenv("MAX_AGENT_ITERATIONS", "5")),
        checker_prompt_version=os.getenv("CHECKER_PROMPT_VERSION", "v2"),
        # Any OpenAI-compatible endpoint (e.g. Databricks Model Serving)
        # can be swapped in here without touching agent code. Blank/unset
        # means "use OpenAI's own API" (the openai SDK default).
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
