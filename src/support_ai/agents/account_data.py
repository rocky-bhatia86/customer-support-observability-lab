"""AccountDataAgent: looks up simulated billing/subscription records for a
ticket's linked account. No LLM call -- deterministic lookup, mirroring a
real system's "generate + execute a query" step without needing a live DB.
"""
from __future__ import annotations

import json
from pathlib import Path

from support_ai.models import AccountDataResult, Ticket

_ACCOUNTS_PATH = Path(__file__).resolve().parents[3] / "data" / "accounts.json"


def _load_accounts() -> dict[str, dict]:
    raw = json.loads(_ACCOUNTS_PATH.read_text())
    return {a["account_id"]: a for a in raw}


class AccountDataAgent:
    def lookup(self, ticket: Ticket) -> AccountDataResult:
        record = _load_accounts().get(ticket.account_id) if ticket.account_id else None
        if not record:
            return AccountDataResult(matched=False)
        return AccountDataResult(
            matched=True,
            account_id=record["account_id"],
            plan=record["plan"],
            subscription_status=record["subscription_status"],
            recent_charges=record["recent_charges"],
            refund_eligible_days=record.get("refund_eligible_days"),
        )
