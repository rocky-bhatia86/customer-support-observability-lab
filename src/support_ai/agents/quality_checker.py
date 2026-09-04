"""QualityCheckerAgent: decides ACCEPT vs REJECT_AND_RETRIEVE for a draft.

Supports CHECKER_PROMPT_VERSION v1 (baseline) and v2 (deliberately stricter --
used in the failure-scenarios branch to simulate a prompt/model regression).
"""
from __future__ import annotations

import json

from support_ai.config import Config
from support_ai.llm_client import call_llm
from support_ai.models import CheckerVerdict, KBArticle, Ticket

_V1_SYSTEM_PROMPT = (
    "You are a quality reviewer for customer support responses. Given the "
    "customer ticket, the knowledge base articles available, and a draft "
    "reply, decide whether the draft is good enough to send.\n\n"
    "Accept the draft if it: is relevant to the ticket, is grounded in the "
    "provided KB articles (no invented policy), and reasonably addresses "
    "the customer's main question, even if some minor detail is phrased "
    "generally rather than with an exact number.\n\n"
    "Respond ONLY with JSON: {\"verdict\": \"ACCEPT\" or "
    "\"REJECT_AND_RETRIEVE\", \"reason\": \"short reason\"}."
)

_V2_SYSTEM_PROMPT = (
    "You are a strict quality reviewer for customer support responses. "
    "Given the customer ticket, the knowledge base articles available, and "
    "a draft reply, decide whether the draft is good enough to send.\n\n"
    "Apply a strict standard. REJECT_AND_RETRIEVE unless ALL of the "
    "following hold:\n"
    "1. The draft addresses every distinct question or issue raised in the "
    "ticket, with no part left unanswered.\n"
    "2. Whenever the customer asks for an exact number, date, or timeframe, "
    "the draft provides that exact figure. A vague phrase like 'a few "
    "business days' does NOT satisfy a request for an exact number and "
    "must be rejected.\n"
    "3. The draft explicitly references which KB article(s) support each "
    "claim.\n\n"
    "Respond ONLY with JSON: {\"verdict\": \"ACCEPT\" or "
    "\"REJECT_AND_RETRIEVE\", \"reason\": \"short reason\"}."
)


def _format_articles(articles: list[KBArticle]) -> str:
    if not articles:
        return "No knowledge base articles were found."
    blocks = [f"[{a.id}] {a.title}\n{a.content}" for a in articles]
    return "\n\n".join(blocks)


class QualityCheckerAgent:
    def __init__(self, config: Config):
        self.config = config

    def check(self, ticket: Ticket, draft_text: str, articles: list[KBArticle]) -> CheckerVerdict:
        system_prompt = (
            _V2_SYSTEM_PROMPT if self.config.checker_prompt_version == "v2" else _V1_SYSTEM_PROMPT
        )
        user_content = (
            f"Customer ticket:\n{ticket.text}\n\n"
            f"Knowledge base articles:\n{_format_articles(articles)}\n\n"
            f"Draft reply:\n{draft_text}"
        )
        result = call_llm(
            self.config,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
        )
        verdict, reason = _parse_verdict(result.text)
        return CheckerVerdict(
            verdict=verdict,
            reason=reason,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )


def _parse_verdict(raw_text: str) -> tuple[str, str]:
    try:
        payload = json.loads(raw_text)
        verdict = payload.get("verdict", "").strip().upper()
        reason = payload.get("reason", "")
    except (json.JSONDecodeError, AttributeError):
        verdict, reason = "", raw_text

    if verdict not in ("ACCEPT", "REJECT_AND_RETRIEVE"):
        verdict = "ACCEPT" if "ACCEPT" in raw_text.upper() else "REJECT_AND_RETRIEVE"
    return verdict, reason
