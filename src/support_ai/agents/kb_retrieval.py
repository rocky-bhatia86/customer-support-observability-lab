"""KBRetrievalAgent: the only agent that calls the KB search tool.

Kept intentionally thin and visible (no hidden abstraction) so that later
instrumentation can see exactly when and how often retrieval happens.

failure-scenarios addition (Failure C): retrieval for a specific, known
ticket id deterministically fails once and succeeds on retry, simulating a
transient KB backend error. This only ever triggers on the ticket's first
retrieval call within a run.
"""
from __future__ import annotations

from support_ai.models import RetrievalResult
from support_ai.tools.kb_search import KBSearchError, search

_SIMULATED_ERROR_TICKET_IDS = {"TCK-002"}


class KBRetrievalAgent:
    def __init__(self):
        self._error_already_simulated: set[str] = set()

    def retrieve(self, category: str, query: str, ticket_id: str | None = None) -> RetrievalResult:
        should_simulate_error = (
            ticket_id in _SIMULATED_ERROR_TICKET_IDS
            and ticket_id not in self._error_already_simulated
        )

        if should_simulate_error:
            self._error_already_simulated.add(ticket_id)
            try:
                search(category, query, simulate_error=True)
            except KBSearchError as exc:
                articles, matched_ids = search(category, query)
                return RetrievalResult(
                    query=query,
                    category=category,
                    articles=articles,
                    matched_ids=matched_ids,
                    error=str(exc),
                    retried=True,
                )

        articles, matched_ids = search(category, query)
        return RetrievalResult(
            query=query,
            category=category,
            articles=articles,
            matched_ids=matched_ids,
        )
