"""ImpactDiagnosticsAgent: checks whether a ticket matches a known/active
technical incident, via the MCP tool server (support_ai.mcp_server) --
mirrors a real system's lineage/impact-analysis agent without needing one,
and is now callable by any MCP client, not just this agent.
"""
from __future__ import annotations

from langfuse import get_client, observe

from support_ai.mcp_client import call_tool
from support_ai.models import ImpactResult, Ticket


class ImpactDiagnosticsAgent:
    @observe(as_type="tool", name="impact_diagnostics.check", capture_input=False, capture_output=False)
    def check(self, ticket: Ticket, category: str) -> ImpactResult:
        get_client().update_current_span(input={"ticket_id": ticket.id, "category": category})
        result = call_tool("check_known_incidents", {"query": ticket.text})
        if not result.get("matched"):
            get_client().update_current_span(output={"matched": False})
            return ImpactResult(matched=False)

        data = ImpactResult(
            matched=True,
            incident_id=result["incident_id"],
            title=result["title"],
            status=result["status"],
            description=result["description"],
        )
        get_client().update_current_span(
            output={"matched": True, "incident_id": data.incident_id, "status": data.status},
        )
        return data
