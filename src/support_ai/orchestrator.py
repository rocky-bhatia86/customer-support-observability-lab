"""WorkflowRunner: the state machine that wires the four agents together.

classify -> retrieve -> draft -> check -> (accept | retry up to
MAX_AGENT_ITERATIONS). This file owns routing and the iteration safety limit;
each agent stays independent and testable on its own.
"""
from __future__ import annotations

import time

from support_ai.agents.drafter import DrafterAgent
from support_ai.agents.kb_retrieval import KBRetrievalAgent
from support_ai.agents.orchestrator import OrchestratorAgent
from support_ai.agents.quality_checker import QualityCheckerAgent
from support_ai.config import Config
from support_ai.models import Ticket, WorkflowResult, WorkflowStep

_ESCALATION_MESSAGE = (
    "Thanks for your patience -- your request needs a closer look from our "
    "support team. We've escalated it and someone will follow up directly."
)


class WorkflowRunner:
    def __init__(self, config: Config):
        self.config = config
        self.orchestrator_agent = OrchestratorAgent(config)
        self.retrieval_agent = KBRetrievalAgent()
        self.drafter_agent = DrafterAgent(config)
        self.checker_agent = QualityCheckerAgent(config)

    def run(self, ticket: Ticket) -> WorkflowResult:
        start_time = time.monotonic()
        steps: list[WorkflowStep] = []

        category_value, _classify_result = self._timed(
            steps, 0, "orchestrator", "classify",
            lambda: self.orchestrator_agent.classify(ticket),
        )

        last_draft_text = ""
        status = "ESCALATED_MAX_ITERATIONS"
        # Failure B (context/token bloat): every retry's retrieved articles
        # are appended here rather than replacing the previous iteration's,
        # so later iterations feed a steadily growing context into the
        # Drafter and Checker even though baseline behavior would just use
        # the freshest retrieval each time.
        accumulated_articles = []

        for iteration in range(1, self.config.max_agent_iterations + 1):
            retrieval = self._timed(
                steps, iteration, "kb_retrieval", "retrieve",
                lambda: self.retrieval_agent.retrieve(category_value, ticket.text, ticket.id),
            )
            accumulated_articles = accumulated_articles + retrieval.articles

            draft = self._timed(
                steps, iteration, "drafter", "draft",
                lambda: self.drafter_agent.draft(ticket, category_value, accumulated_articles),
            )
            last_draft_text = draft.text

            verdict = self._timed(
                steps, iteration, "quality_checker", "check",
                lambda: self.checker_agent.check(ticket, draft.text, accumulated_articles),
            )

            if verdict.verdict == "ACCEPT":
                status = "RESOLVED"
                break

        final_response = last_draft_text if status == "RESOLVED" else _ESCALATION_MESSAGE

        elapsed = time.monotonic() - start_time
        return WorkflowResult(
            ticket_id=ticket.id,
            category=category_value,
            status=status,
            final_response=final_response,
            iterations=steps[-1].iteration if steps else 0,
            elapsed_seconds=elapsed,
            steps=steps,
        )

    @staticmethod
    def _timed(steps: list[WorkflowStep], iteration: int, agent: str, action: str, fn):
        step_start = time.monotonic()
        result = fn()
        elapsed = time.monotonic() - step_start

        prompt_tokens = getattr(result, "prompt_tokens", 0)
        completion_tokens = getattr(result, "completion_tokens", 0)
        if isinstance(result, tuple):
            # OrchestratorAgent.classify returns (category, LLMResult)
            llm_result = result[1]
            prompt_tokens = getattr(llm_result, "prompt_tokens", 0)
            completion_tokens = getattr(llm_result, "completion_tokens", 0)
            detail = f"category={result[0]}"
        elif action == "retrieve":
            detail = f"matched_ids={result.matched_ids}"
            if result.retried:
                detail += f" retried_after_error={result.error!r}"
        elif action == "draft":
            detail = f"chars={len(result.text)}"
        elif action == "check":
            detail = f"verdict={result.verdict} reason={result.reason}"
        else:
            detail = ""

        steps.append(WorkflowStep(
            iteration=iteration,
            agent=agent,
            action=action,
            detail=detail,
            elapsed_seconds=elapsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ))
        return result
