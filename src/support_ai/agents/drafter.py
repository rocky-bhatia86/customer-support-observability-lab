"""DrafterAgent: writes a customer-facing response grounded in retrieved KB
articles. Must not invent policy or claim an action was completed unless the
KB/context supports it."""
from __future__ import annotations

from support_ai.config import Config
from support_ai.llm_client import call_llm
from support_ai.models import DraftResult, KBArticle, Ticket

_SYSTEM_PROMPT = (
    "You are a customer support agent writing a reply to a customer ticket. "
    "You must ground your answer strictly in the knowledge base articles "
    "provided below. Do not invent policy details, exact numbers, or "
    "timeframes that are not stated in the articles. Do not claim that an "
    "account action (refund, cancellation, password reset) has already been "
    "completed -- only describe what will happen or what the customer should "
    "do next. Be concise and empathetic."
)


def _format_articles(articles: list[KBArticle]) -> str:
    if not articles:
        return "No knowledge base articles were found."
    blocks = [f"[{a.id}] {a.title}\n{a.content}" for a in articles]
    return "\n\n".join(blocks)


class DrafterAgent:
    def __init__(self, config: Config):
        self.config = config

    def draft(self, ticket: Ticket, category: str, articles: list[KBArticle]) -> DraftResult:
        user_content = (
            f"Ticket category: {category}\n"
            f"Customer ticket:\n{ticket.text}\n\n"
            f"Knowledge base articles:\n{_format_articles(articles)}"
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
