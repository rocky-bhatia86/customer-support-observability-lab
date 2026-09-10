"""AccountDataAgent: looks up simulated billing/subscription records for a
ticket's linked account, via the MCP tool server (support_ai.mcp_server) --
mirrors a real system's "generate + execute a query" step without needing
a live DB, and is now callable by any MCP client, not just this agent.
"""
from __future__ import annotations

from support_ai.mcp_client import call_tool
from support_ai.models import AccountDataResult, Ticket


class AccountDataAgent:
    def lookup(self, ticket: Ticket) -> AccountDataResult:
        if not ticket.account_id:
            return AccountDataResult(matched=False)

        result = call_tool("lookup_account_data", {"account_id": ticket.account_id})
        if not result.get("matched"):
            return AccountDataResult(matched=False)

        return AccountDataResult(
            matched=True,
            account_id=result["account_id"],
            plan=result["plan"],
            subscription_status=result["subscription_status"],
            recent_charges=result["recent_charges"],
            refund_eligible_days=result.get("refund_eligible_days"),
        )
