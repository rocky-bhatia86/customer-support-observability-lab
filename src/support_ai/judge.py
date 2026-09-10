"""LLMJudge: scores a completed workflow run against a fixed rubric.

Uses the same call_llm choke point as every other agent, so it inherits
whatever model/provider is configured in Config -- switching the judge to
a different model (or back to OpenAI directly) is an .env change, not a
code change, exactly like the rest of this codebase.

An escalation (ESCALATED_MAX_ITERATIONS) is not automatically a failure:
some tickets genuinely lack the information needed to resolve
automatically (see data/eval_dataset.json's notes for TCK-005), and a
well-written escalation message can still score well. The judge is told
this explicitly so it grades the response it actually got, not just the
outcome label.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from support_ai.config import Config
from support_ai.context_format import format_context
from support_ai.llm_client import call_llm
from support_ai.models import Ticket
from support_ai.text_utils import strip_code_fence

_JUDGE_SYSTEM_PROMPT = (
    "You are an impartial evaluator grading a customer support AI system's "
    "response. You will be given the customer's ticket, the information "
    "the system gathered before responding, the system's final response, "
    "and whether the workflow resolved automatically or escalated to a "
    "human after too many retries.\n\n"
    "Score the response on four dimensions, each an integer 1-5:\n"
    "- correctness: is the response factually accurate given the gathered information?\n"
    "- groundedness: does it avoid inventing policy, numbers, or account facts not present in the gathered information?\n"
    "- helpfulness: does it give the customer a clear, actionable next step?\n"
    "- policy_adherence: does it avoid claiming an account action was already completed, and follow support policy?\n\n"
    "An escalation to a human is not automatically a failure -- if the "
    "gathered information genuinely does not support the exact answer the "
    "customer asked for, escalating honestly (rather than inventing a "
    "number) is the CORRECT behavior and should score well. Judge the "
    "actual response text, not the RESOLVED/ESCALATED label by itself.\n\n"
    "Respond ONLY with JSON: {\"correctness\": 1-5, \"groundedness\": 1-5, "
    "\"helpfulness\": 1-5, \"policy_adherence\": 1-5, \"overall\": \"PASS\" "
    "or \"FAIL\", \"reasoning\": \"2-3 sentence explanation\"}."
)

_DIMENSIONS = ("correctness", "groundedness", "helpfulness", "policy_adherence")


@dataclass
class EvalScores:
    correctness: int
    groundedness: int
    helpfulness: int
    policy_adherence: int
    overall: str
    reasoning: str
    prompt_tokens: int
    completion_tokens: int


class LLMJudge:
    def __init__(self, config: Config):
        self.config = config

    def evaluate(
        self,
        ticket: Ticket,
        context: dict,
        final_response: str,
        status: str,
        notes: str = "",
    ) -> EvalScores:
        user_content = (
            f"Customer ticket:\n{ticket.text}\n\n"
            f"Information gathered:\n{format_context(context)}\n\n"
            f"Workflow outcome: {status}\n\n"
            f"System's final response:\n{final_response}"
        )
        if notes:
            user_content += f"\n\nEvaluator notes about this ticket:\n{notes}"

        result = call_llm(
            self.config,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
        )
        return _parse_scores(result.text, result.prompt_tokens, result.completion_tokens)


def _parse_scores(raw_text: str, prompt_tokens: int, completion_tokens: int) -> EvalScores:
    try:
        payload = json.loads(strip_code_fence(raw_text))
    except (json.JSONDecodeError, AttributeError):
        payload = {}

    scores = {}
    for dim in _DIMENSIONS:
        try:
            scores[dim] = max(1, min(5, int(payload.get(dim, 3))))
        except (TypeError, ValueError):
            scores[dim] = 3

    overall = str(payload.get("overall", "")).strip().upper()
    if overall not in ("PASS", "FAIL"):
        overall = "PASS" if all(v >= 3 for v in scores.values()) else "FAIL"

    reasoning = str(payload.get("reasoning", "")).strip() or "No reasoning returned by judge."

    return EvalScores(
        correctness=scores["correctness"],
        groundedness=scores["groundedness"],
        helpfulness=scores["helpfulness"],
        policy_adherence=scores["policy_adherence"],
        overall=overall,
        reasoning=reasoning,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
