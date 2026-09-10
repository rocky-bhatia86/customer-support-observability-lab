"""ImpactDiagnosticsAgent: checks whether a ticket matches a known/active
technical incident, via the MCP tool server (support_ai.mcp_server) --
mirrors a real system's lineage/impact-analysis agent without needing one,
and is now callable by any MCP client, not just this agent.
"""
from __future__ import annotations

from support_ai.mcp_client import call_tool
from support_ai.models import ImpactResult, Ticket


class ImpactDiagnosticsAgent:
    def check(self, ticket: Ticket, category: str) -> ImpactResult:
        result = call_tool("check_known_incidents", {"query": ticket.text})
        if not result.get("matched"):
            return ImpactResult(matched=False)

        return ImpactResult(
            matched=True,
            incident_id=result["incident_id"],
            title=result["title"],
            status=result["status"],
            description=result["description"],
        )
