"""OrchestratorAgent: classifies an incoming ticket. Routing/looping is
handled by support_ai.orchestrator.WorkflowRunner, not here."""
from __future__ import annotations

from support_ai.config import Config
from support_ai.llm_client import LLMResult, call_llm
from support_ai.models import Ticket

_CATEGORIES = ("billing", "bug", "how-to")

_SYSTEM_PROMPT = (
    "You are a support ticket classifier. Read the customer ticket and "
    "respond with exactly one word: billing, bug, or how-to. "
    "Choose the single best-fitting category even if the ticket touches "
    "more than one area."
)


class OrchestratorAgent:
    def __init__(self, config: Config):
        self.config = config

    def classify(self, ticket: Ticket) -> tuple[str, LLMResult]:
        result = call_llm(
            self.config,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": ticket.text},
            ],
            temperature=0,
        )
        category = result.text.strip().lower()
        if category not in _CATEGORIES:
            category = "how-to"
        return category, result
