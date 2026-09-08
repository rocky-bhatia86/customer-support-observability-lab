"""AccountAccessAgent: looks up a customer's account login/lockout status.
Same shape as AccountDataAgent but a separate dataset/agent, since access
state and billing state are different systems in a real support platform.
"""
from __future__ import annotations

import json
from pathlib import Path

from support_ai.models import AccessResult, Ticket

_ACCESS_PATH = Path(__file__).resolve().parents[3] / "data" / "access_records.json"


def _load_records() -> dict[str, dict]:
    raw = json.loads(_ACCESS_PATH.read_text())
    return {r["account_id"]: r for r in raw}


class AccountAccessAgent:
    def check(self, ticket: Ticket) -> AccessResult:
        record = _load_records().get(ticket.account_id) if ticket.account_id else None
        if not record:
            return AccessResult(matched=False)
        return AccessResult(
            matched=True,
            account_id=record["account_id"],
            locked=record["locked"],
            failed_login_attempts=record["failed_login_attempts"],
            mfa_enabled=record["mfa_enabled"],
            last_login=record.get("last_login"),
        )
