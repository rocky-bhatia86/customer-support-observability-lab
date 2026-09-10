"""QualityCheckerAgent: decides ACCEPT vs REJECT_AND_RETRIEVE for a draft.

Supports CHECKER_PROMPT_VERSION v1 (baseline) and v2 (deliberately stricter --
used in the failure-scenarios branch to simulate a prompt/model regression).

The two prompt texts are managed in Langfuse Prompt Management (see
scripts/seed_prompts.py), fetched by label ("v1"/"v2") -- this makes
Failure D ("last week's prompt bump") a real, inspectable prompt version
history in the Langfuse UI rather than two Python string constants. Falls
back to the hardcoded text below if Langfuse is unreachable or the prompt
hasn't been seeded yet, so the checker still works either way.
"""
from __future__ import annotations

import json

from langfuse import get_client, observe

from support_ai.config import Config
from support_ai.context_format import format_context
from support_ai.llm_client import call_llm
from support_ai.models import CheckerVerdict, Ticket
from support_ai.text_utils import strip_code_fence

_PROMPT_NAME = "quality_checker_system_prompt"

_FALLBACK_PROMPTS = {
    "v1": (
        "You are a quality reviewer for customer support responses. Given the "
        "customer ticket, the supporting information gathered for it, and a "
        "draft reply, decide whether the draft is good enough to send.\n\n"
        "Accept the draft if it: is relevant to the ticket, is grounded in the "
        "provided information (no invented policy or invented data), and "
        "reasonably addresses the customer's main question, even if some minor "
        "detail is phrased generally rather than with an exact number.\n\n"
        "Respond ONLY with JSON: {\"verdict\": \"ACCEPT\" or "
        "\"REJECT_AND_RETRIEVE\", \"reason\": \"short reason\"}."
    ),
    "v2": (
        "You are a strict quality reviewer for customer support responses. "
        "Given the customer ticket, the supporting information gathered for it, "
        "and a draft reply, decide whether the draft is good enough to send.\n\n"
        "Apply a strict standard. REJECT_AND_RETRIEVE unless ALL of the "
        "following hold:\n"
        "1. The draft addresses every distinct question or issue raised in the "
        "ticket, with no part left unanswered.\n"
        "2. Whenever the customer asks for an exact number, date, or timeframe, "
        "the draft provides that exact figure. A vague phrase like 'a few "
        "business days' does NOT satisfy a request for an exact number and "
        "must be rejected.\n"
        "3. The draft explicitly references which source (KB article id, "
        "account record, or incident id) supports each claim.\n\n"
        "Respond ONLY with JSON: {\"verdict\": \"ACCEPT\" or "
        "\"REJECT_AND_RETRIEVE\", \"reason\": \"short reason\"}."
    ),
}


def _fetch_prompt(label: str):
    """Returns (system_prompt_text, prompt_client_or_None). Falls back to
    the hardcoded text (prompt_client=None) if Langfuse can't serve it."""
    try:
        prompt_client = get_client().get_prompt(_PROMPT_NAME, label=label)
        return prompt_client.prompt, prompt_client
    except Exception:  # noqa: BLE001 - any fetch failure falls back, never breaks the checker
        return _FALLBACK_PROMPTS.get(label, _FALLBACK_PROMPTS["v1"]), None


class QualityCheckerAgent:
    def __init__(self, config: Config):
        self.config = config

    @observe(as_type="agent", name="quality_checker.check", capture_input=False, capture_output=False)
    def check(
        self, ticket: Ticket, draft_text: str, context: dict, iteration: int = 0,
    ) -> CheckerVerdict:
        system_prompt, prompt_client = _fetch_prompt(self.config.checker_prompt_version)
        user_content = (
            f"Customer ticket:\n{ticket.text}\n\n"
            f"Information gathered:\n{format_context(context)}\n\n"
            f"Draft reply:\n{draft_text}"
        )
        result = call_llm(
            self.config,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            version=self.config.checker_prompt_version,
            prompt=prompt_client,
        )
        verdict, reason = _parse_verdict(result.text)
        get_client().update_current_span(
            input={"ticket_id": ticket.id, "iteration": iteration},
            output={"verdict": verdict, "reason": reason},
            metadata={
                "iteration": iteration,
                "checker_prompt_version": self.config.checker_prompt_version,
            },
        )
        return CheckerVerdict(
            verdict=verdict,
            reason=reason,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )


def _parse_verdict(raw_text: str) -> tuple[str, str]:
    try:
        payload = json.loads(strip_code_fence(raw_text))
        verdict = payload.get("verdict", "").strip().upper()
        reason = payload.get("reason", "")
    except (json.JSONDecodeError, AttributeError):
        verdict, reason = "", raw_text

    if verdict not in ("ACCEPT", "REJECT_AND_RETRIEVE"):
        verdict = "ACCEPT" if "ACCEPT" in raw_text.upper() else "REJECT_AND_RETRIEVE"
    return verdict, reason
