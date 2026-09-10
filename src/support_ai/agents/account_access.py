"""AccountAccessAgent: looks up a customer's account login/lockout status,
via the MCP tool server (support_ai.mcp_server). Same shape as
AccountDataAgent but a separate tool, since access state and billing state
are different systems in a real support platform.
"""
from __future__ import annotations

from langfuse import get_client, observe

from support_ai.mcp_client import call_tool
from support_ai.models import AccessResult, Ticket


class AccountAccessAgent:
    @observe(as_type="tool", name="account_access.check", capture_input=False, capture_output=False)
    def check(self, ticket: Ticket) -> AccessResult:
        get_client().update_current_span(input={"ticket_id": ticket.id, "account_id": ticket.account_id})
        if not ticket.account_id:
            get_client().update_current_span(output={"matched": False})
            return AccessResult(matched=False)

        result = call_tool("check_account_access", {"account_id": ticket.account_id})
        if not result.get("matched"):
            get_client().update_current_span(output={"matched": False})
            return AccessResult(matched=False)

        data = AccessResult(
            matched=True,
            account_id=result["account_id"],
            locked=result["locked"],
            failed_login_attempts=result["failed_login_attempts"],
            mfa_enabled=result["mfa_enabled"],
            last_login=result.get("last_login"),
        )
        get_client().update_current_span(
            output={"matched": True, "locked": data.locked, "failed_login_attempts": data.failed_login_attempts},
        )
        return data
