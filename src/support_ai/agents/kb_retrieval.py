"""KBRetrievalAgent: the only agent that calls the KB search tool.

Kept intentionally thin and visible (no hidden abstraction) so that later
instrumentation can see exactly when and how often retrieval happens.
"""
from __future__ import annotations

from support_ai.models import RetrievalResult
from support_ai.tools.kb_search import search


class KBRetrievalAgent:
    def retrieve(self, category: str, query: str) -> RetrievalResult:
        articles, matched_ids = search(category, query)
        return RetrievalResult(
            query=query,
            category=category,
            articles=articles,
            matched_ids=matched_ids,
        )
