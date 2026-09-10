"""DrafterAgent: writes a customer-facing response grounded in whatever the
specialist agents (kb_retrieval, account_data, impact_diagnostics,
account_access) gathered for this ticket. Must not invent policy or claim an
action was completed unless the gathered context supports it."""
from __future__ import annotations

from langfuse import get_client, observe

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

    @observe(as_type="agent", name="drafter.draft", capture_input=False, capture_output=False)
    def draft(self, ticket: Ticket, category: str, context: dict) -> DraftResult:
        get_client().update_current_span(
            input={
                "ticket_id": ticket.id,
                "category": category,
                "kb_article_ids": [a.id for a in (context.get("kb_articles") or [])],
                "account_data_matched": bool(context.get("account_data") and context["account_data"].matched),
                "impact_matched": bool(context.get("impact") and context["impact"].matched),
                "access_matched": bool(context.get("access") and context["access"].matched),
            },
        )
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
        get_client().update_current_span(output=result.text)
        return DraftResult(
            text=result.text,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )
