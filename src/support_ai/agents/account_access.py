"""AccountAccessAgent: looks up a customer's account login/lockout status,
via the MCP tool server (support_ai.mcp_server). Same shape as
AccountDataAgent but a separate tool, since access state and billing state
are different systems in a real support platform.
"""
from __future__ import annotations

from support_ai.mcp_client import call_tool
from support_ai.models import AccessResult, Ticket


class AccountAccessAgent:
    def check(self, ticket: Ticket) -> AccessResult:
        if not ticket.account_id:
            return AccessResult(matched=False)

        result = call_tool("check_account_access", {"account_id": ticket.account_id})
        if not result.get("matched"):
            return AccessResult(matched=False)

        return AccessResult(
            matched=True,
            account_id=result["account_id"],
            locked=result["locked"],
            failed_login_attempts=result["failed_login_attempts"],
            mfa_enabled=result["mfa_enabled"],
            last_login=result.get("last_login"),
        )
