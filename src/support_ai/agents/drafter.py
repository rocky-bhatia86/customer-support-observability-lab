"""DrafterAgent: writes a customer-facing response grounded in whatever the
specialist agents (kb_retrieval, account_data, impact_diagnostics,
account_access) gathered for this ticket. Must not invent policy or claim an
action was completed unless the gathered context supports it."""
from __future__ import annotations

from support_ai.config import Config
from support_ai.context_format import format_context
from support_ai.llm_client import call_llm
from support_ai.models import DraftResult, Ticket

_SYSTEM_PROMPT = (
    "You are a customer support agent writing a reply to a customer ticket. "
    "You must ground your answer strictly in the information gathered below "
    "(knowledge base articles, account records, incident reports, access "
    "status -- whichever are present). Do not invent policy details, exact "
    "numbers, timeframes, or account facts that are not stated in the "
    "gathered information. Do not claim that an account action (refund, "
    "cancellation, password reset) has already been completed -- only "
    "describe what will happen or what the customer should do next. Be "
    "concise and empathetic."
)


class DrafterAgent:
    def __init__(self, config: Config):
        self.config = config

    def draft(self, ticket: Ticket, category: str, context: dict) -> DraftResult:
        user_content = (
            f"Ticket category: {category}\n"
            f"Customer ticket:\n{ticket.text}\n\n"
            f"Information gathered:\n{format_context(context)}"
        )
        result = call_llm(
            self.config,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        return DraftResult(
            text=result.text,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )
