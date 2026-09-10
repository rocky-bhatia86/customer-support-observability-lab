"""WorkflowRunner: the state machine that wires the agents together.

classify (which also decides the specialist-agent plan) -> run whichever of
{kb_retrieval, account_data, impact_diagnostics, account_access} the plan
calls for -> draft -> check -> (accept | retry up to MAX_AGENT_ITERATIONS).
This file owns routing and the iteration safety limit; each agent stays
independent and testable on its own.

Not every ticket runs the same specialist agents -- the plan comes from
OrchestratorAgent.classify, so a simple how-to ticket might only run
kb_retrieval, while a ticket combining a billing dispute with access issues
might run account_data AND account_access together. Draft and quality-check
always run every iteration regardless of the plan.
"""
from __future__ import annotations

import time

from langfuse import get_client, observe

from support_ai.agents.account_access import AccountAccessAgent
from support_ai.agents.account_data import AccountDataAgent
from support_ai.agents.drafter import DrafterAgent
from support_ai.agents.impact_diagnostics import ImpactDiagnosticsAgent
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
        self.kb_agent = KBRetrievalAgent()
        self.account_data_agent = AccountDataAgent()
        self.impact_agent = ImpactDiagnosticsAgent()
        self.access_agent = AccountAccessAgent()
        self.drafter_agent = DrafterAgent(config)
        self.checker_agent = QualityCheckerAgent(config)

    @observe(name="support_ticket_workflow", as_type="span", capture_input=False, capture_output=False)
    def run(self, ticket: Ticket, on_step=None) -> WorkflowResult:
        langfuse = get_client()
        langfuse.update_current_span(
            input={"ticket_id": ticket.id, "ticket_text": ticket.text},
            metadata={
                "ticket_id": ticket.id,
                "model_name": self.config.model_name,
                "checker_prompt_version": self.config.checker_prompt_version,
                "max_agent_iterations": self.config.max_agent_iterations,
            },
        )
        start_time = time.monotonic()
        steps: list[WorkflowStep] = []

        category_value, agent_plan, _classify_result = self._timed(
            steps, 0, "orchestrator", "classify",
            lambda: self.orchestrator_agent.classify(ticket),
            on_step,
        )

        last_draft_text = ""
        status = "ESCALATED_MAX_ITERATIONS"
        # Failure B (context/token bloat): every retry's retrieved KB
        # articles are appended here rather than replacing the previous
        # iteration's, so later iterations feed a steadily growing context
        # into the Drafter and Checker even though baseline behavior would
        # just use the freshest retrieval each time. The other specialist
        # results are fixed-size records, so they're refreshed (not
        # accumulated) each iteration.
        accumulated_articles = []
        context: dict = {
            "kb_articles": [],
            "account_data": None,
            "impact": None,
            "access": None,
        }

        for iteration in range(1, self.config.max_agent_iterations + 1):
            with langfuse.start_as_current_observation(
                name=f"iteration_{iteration}", as_type="span",
                input={"iteration": iteration, "agent_plan": agent_plan},
            ):
                if "kb_retrieval" in agent_plan:
                    retrieval = self._timed(
                        steps, iteration, "kb_retrieval", "retrieve",
                        lambda: self.kb_agent.retrieve(category_value, ticket.text, ticket.id),
                        on_step,
                    )
                    accumulated_articles = accumulated_articles + retrieval.articles
                    context["kb_articles"] = accumulated_articles

                if "account_data" in agent_plan:
                    context["account_data"] = self._timed(
                        steps, iteration, "account_data", "lookup",
                        lambda: self.account_data_agent.lookup(ticket),
                        on_step,
                    )

                if "impact_diagnostics" in agent_plan:
                    context["impact"] = self._timed(
                        steps, iteration, "impact_diagnostics", "check",
                        lambda: self.impact_agent.check(ticket, category_value),
                        on_step,
                    )

                if "account_access" in agent_plan:
                    context["access"] = self._timed(
                        steps, iteration, "account_access", "check",
                        lambda: self.access_agent.check(ticket),
                        on_step,
                    )

                draft = self._timed(
                    steps, iteration, "drafter", "draft",
                    lambda: self.drafter_agent.draft(ticket, category_value, context),
                    on_step,
                )
                last_draft_text = draft.text

                verdict = self._timed(
                    steps, iteration, "quality_checker", "check",
                    lambda: self.checker_agent.check(ticket, draft.text, context, iteration),
                    on_step,
                )

            if verdict.verdict == "ACCEPT":
                status = "RESOLVED"
                break

        final_response = last_draft_text if status == "RESOLVED" else _ESCALATION_MESSAGE

        elapsed = time.monotonic() - start_time
        iterations = steps[-1].iteration if steps else 0

        langfuse.update_current_span(
            output={"status": status, "final_response": final_response},
            metadata={
                "ticket_id": ticket.id,
                "category": category_value,
                "status": status,
                "iterations": iterations,
                "elapsed_seconds": elapsed,
                "model_name": self.config.model_name,
                "checker_prompt_version": self.config.checker_prompt_version,
            },
        )

        return WorkflowResult(
            ticket_id=ticket.id,
            category=category_value,
            status=status,
            final_response=final_response,
            iterations=iterations,
            elapsed_seconds=elapsed,
            steps=steps,
            trace_id=langfuse.get_current_trace_id(),
            context=context,
        )

    @staticmethod
    def _timed(steps: list[WorkflowStep], iteration: int, agent: str, action: str, fn, on_step=None):
        step_start = time.monotonic()
        result = fn()
        elapsed = time.monotonic() - step_start

        prompt_tokens = getattr(result, "prompt_tokens", 0)
        completion_tokens = getattr(result, "completion_tokens", 0)
        meta: dict = {}

        if agent == "orchestrator":
            category, agents_plan, llm_result = result
            prompt_tokens = getattr(llm_result, "prompt_tokens", 0)
            completion_tokens = getattr(llm_result, "completion_tokens", 0)
            detail = f"category={category} agents={agents_plan}"
            meta = {"category": category, "agents": agents_plan}
        elif agent == "kb_retrieval":
            detail = f"matched_ids={result.matched_ids}"
            if result.retried:
                detail += f" retried_after_error={result.error!r}"
            meta = {
                "matched_ids": result.matched_ids,
                "retried": result.retried,
                "error": result.error,
            }
        elif agent == "account_data":
            detail = f"matched={result.matched} account_id={result.account_id}"
            meta = {
                "matched": result.matched,
                "account_id": result.account_id,
                "plan": result.plan,
                "subscription_status": result.subscription_status,
                "recent_charges": result.recent_charges,
                "refund_eligible_days": result.refund_eligible_days,
            }
        elif agent == "impact_diagnostics":
            detail = f"matched={result.matched} incident_id={result.incident_id}"
            meta = {
                "matched": result.matched,
                "incident_id": result.incident_id,
                "title": result.title,
                "status": result.status,
            }
        elif agent == "account_access":
            detail = f"matched={result.matched} locked={result.locked}"
            meta = {
                "matched": result.matched,
                "account_id": result.account_id,
                "locked": result.locked,
                "failed_login_attempts": result.failed_login_attempts,
                "mfa_enabled": result.mfa_enabled,
            }
        elif agent == "drafter":
            detail = f"chars={len(result.text)}"
            meta = {"chars": len(result.text)}
        elif agent == "quality_checker":
            detail = f"verdict={result.verdict} reason={result.reason}"
            meta = {"verdict": result.verdict, "reason": result.reason}
        else:
            detail = ""

        step = WorkflowStep(
            iteration=iteration,
            agent=agent,
            action=action,
            detail=detail,
            elapsed_seconds=elapsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            meta=meta,
        )
        steps.append(step)
        if on_step is not None:
            on_step(step)
        return result
