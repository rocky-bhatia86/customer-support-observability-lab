"""KBRetrievalAgent: the only agent that calls the knowledge-base search
tool. Real searches now go through the MCP tool server
(support_ai.mcp_server); the error-simulation path stays local since
"simulate_error" is an internal test hook, not something that belongs on
a tool schema real MCP clients (e.g. Claude Desktop) would see.

failure-scenarios addition (Failure C): retrieval for a specific, known
ticket id deterministically fails once and succeeds on retry, simulating a
transient KB backend error. This only ever triggers on the ticket's first
retrieval call within a run.
"""
from __future__ import annotations

from langfuse import get_client, observe

from support_ai.mcp_client import call_tool
from support_ai.models import KBArticle, RetrievalResult
from support_ai.tools.kb_search import KBSearchError, search

_SIMULATED_ERROR_TICKET_IDS = {"TCK-002"}


def _search_via_mcp(category: str, query: str) -> tuple[list[KBArticle], list[str]]:
    result = call_tool("search_knowledge_base", {"category": category, "query": query})
    articles = [KBArticle(**a) for a in result["articles"]]
    return articles, result["matched_ids"]


class KBRetrievalAgent:
    def __init__(self):
        self._error_already_simulated: set[str] = set()

    @observe(as_type="retriever", name="kb_retrieval.retrieve", capture_output=False)
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
                articles, matched_ids = _search_via_mcp(category, query)
                result = RetrievalResult(
                    query=query,
                    category=category,
                    articles=articles,
                    matched_ids=matched_ids,
                    error=str(exc),
                    retried=True,
                )
                get_client().update_current_span(
                    output={"matched_ids": matched_ids, "retried": True, "error": str(exc)},
                )
                return result

        articles, matched_ids = _search_via_mcp(category, query)
        result = RetrievalResult(
            query=query,
            category=category,
            articles=articles,
            matched_ids=matched_ids,
        )
        get_client().update_current_span(output={"matched_ids": matched_ids, "retried": False})
        return result
