"""Shared text helpers for parsing LLM output."""
from __future__ import annotations


def strip_code_fence(text: str) -> str:
    """Some models (e.g. Claude via Databricks Model Serving) wrap JSON
    responses in markdown code fences even when told to respond with JSON
    only. Strip a leading/trailing ``` fence if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()
