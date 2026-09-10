"""AccountDataAgent: looks up simulated billing/subscription records for a
ticket's linked account, via the MCP tool server (support_ai.mcp_server) --
mirrors a real system's "generate + execute a query" step without needing
a live DB, and is now callable by any MCP client, not just this agent.
"""
from __future__ import annotations

from langfuse import get_client, observe

from support_ai.mcp_client import call_tool
from support_ai.models import AccountDataResult, Ticket


class AccountDataAgent:
    @observe(as_type="tool", name="account_data.lookup", capture_input=False, capture_output=False)
    def lookup(self, ticket: Ticket) -> AccountDataResult:
        get_client().update_current_span(input={"ticket_id": ticket.id, "account_id": ticket.account_id})
        if not ticket.account_id:
            get_client().update_current_span(output={"matched": False})
            return AccountDataResult(matched=False)

        result = call_tool("lookup_account_data", {"account_id": ticket.account_id})
        if not result.get("matched"):
            get_client().update_current_span(output={"matched": False})
            return AccountDataResult(matched=False)

        data = AccountDataResult(
            matched=True,
            account_id=result["account_id"],
            plan=result["plan"],
            subscription_status=result["subscription_status"],
            recent_charges=result["recent_charges"],
            refund_eligible_days=result.get("refund_eligible_days"),
        )
        get_client().update_current_span(
            output={
                "matched": True,
                "account_id": data.account_id,
                "plan": data.plan,
                "refund_eligible_days": data.refund_eligible_days,
            },
        )
        return data
