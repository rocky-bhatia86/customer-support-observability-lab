"""ImpactDiagnosticsAgent: checks whether a ticket matches a known/active
technical incident. Same deterministic keyword-overlap style as
tools/kb_search.py, just against a separate incidents dataset -- mirrors a
real system's lineage/impact-analysis agent without needing one.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from support_ai.models import ImpactResult, Ticket

_INCIDENTS_PATH = Path(__file__).resolve().parents[3] / "data" / "incidents.json"

_STOPWORDS = {
    "a", "an", "the", "is", "was", "were", "i", "my", "me", "to", "for",
    "of", "on", "in", "and", "or", "it", "this", "that", "how", "do", "does",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS}


class ImpactDiagnosticsAgent:
    def check(self, ticket: Ticket, category: str) -> ImpactResult:
        incidents = json.loads(_INCIDENTS_PATH.read_text())
        query_tokens = _tokenize(ticket.text)

        best = None
        best_overlap = 0
        for incident in incidents:
            overlap = len(query_tokens & set(incident["keywords"]))
            if overlap > best_overlap:
                best_overlap = overlap
                best = incident

        if not best:
            return ImpactResult(matched=False)

        return ImpactResult(
            matched=True,
            incident_id=best["incident_id"],
            title=best["title"],
            status=best["status"],
            description=best["description"],
        )
