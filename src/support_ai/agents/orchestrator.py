"""OrchestratorAgent: classifies an incoming ticket AND decides which
specialist agents are actually needed to handle it (dynamic routing).
Looping/execution is handled by support_ai.orchestrator.WorkflowRunner, not
here -- this agent only produces the plan.

Available specialist agents:
- kb_retrieval: help-center knowledge base articles (policies, how-to guides)
- account_data: the customer's real billing/subscription records
- impact_diagnostics: whether the issue matches a known/active incident
- account_access: the customer's account login/lockout status

Not every ticket needs the same combination -- a simple how-to question
might only need kb_retrieval, while a ticket combining a billing dispute
with login errors might need account_data AND impact_diagnostics together.
Drafting and quality-checking always run afterward regardless of which
specialists were chosen.
"""
from __future__ import annotations

import json

from support_ai.config import Config
from support_ai.llm_client import LLMResult, call_llm
from support_ai.models import Ticket
from support_ai.text_utils import strip_code_fence

_CATEGORIES = ("billing", "bug", "how-to")
_ALLOWED_AGENTS = ("kb_retrieval", "account_data", "impact_diagnostics", "account_access")
_DEFAULT_AGENTS = ["kb_retrieval"]

_SYSTEM_PROMPT = (
    "You are the orchestrator for a customer support system with several "
    "specialist agents available:\n"
    "- kb_retrieval: searches help-center knowledge base articles (general "
    "policies, how-to guides)\n"
    "- account_data: looks up the customer's real billing/subscription "
    "records (charges, plan, refund eligibility)\n"
    "- impact_diagnostics: checks whether the issue matches a known/active "
    "technical incident\n"
    "- account_access: looks up the customer's account login/lockout status\n\n"
    "Read the customer ticket and decide:\n"
    "1. The single best-fitting category: billing, bug, or how-to.\n"
    "2. Which of the specialist agents above are actually needed to answer "
    "this ticket. Pick only what's relevant -- a ticket may need just one "
    "agent, or a combination of several. Do not include an agent that "
    "wouldn't help answer this specific ticket.\n\n"
    "Respond ONLY with JSON: {\"category\": \"billing\"|\"bug\"|\"how-to\", "
    "\"agents\": [subset of \"kb_retrieval\", \"account_data\", "
    "\"impact_diagnostics\", \"account_access\"]}."
)


class OrchestratorAgent:
    def __init__(self, config: Config):
        self.config = config

    def classify(self, ticket: Ticket) -> tuple[str, list[str], LLMResult]:
        result = call_llm(
            self.config,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": ticket.text},
            ],
            temperature=0,
        )

        category = "how-to"
        agents = list(_DEFAULT_AGENTS)
        try:
            payload = json.loads(strip_code_fence(result.text))
            parsed_category = str(payload.get("category", "")).strip().lower()
            if parsed_category in _CATEGORIES:
                category = parsed_category
            parsed_agents = [a for a in payload.get("agents", []) if a in _ALLOWED_AGENTS]
            if parsed_agents:
                agents = parsed_agents
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

        return category, agents, result
