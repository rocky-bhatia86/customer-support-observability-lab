"""Formats the combined output of whichever specialist agents ran for a
ticket (kb_retrieval, account_data, impact_diagnostics, account_access) into
a single text block for the Drafter and Quality Checker prompts.

Only sections with actual matched data are included, so a ticket that only
needed one specialist agent doesn't get empty/placeholder sections."""
from __future__ import annotations


def format_context(context: dict) -> str:
    sections: list[str] = []

    articles = context.get("kb_articles") or []
    if articles:
        blocks = [f"[{a.id}] {a.title}\n{a.content}" for a in articles]
        sections.append("Knowledge base articles:\n" + "\n\n".join(blocks))

    account = context.get("account_data")
    if account is not None and account.matched:
        charges = "\n".join(
            f"- {c['date']}: ${c['amount']:.2f} ({c['description']})"
            for c in account.recent_charges
        ) or "No recent charges on file."
        refund_line = (
            f"Refund eligibility window: {account.refund_eligible_days} business days.\n"
            if account.refund_eligible_days is not None
            else "Refund eligibility window: not available for this account -- requires manual review.\n"
        )
        sections.append(
            f"Account billing record (account {account.account_id}, "
            f"plan: {account.plan}, status: {account.subscription_status}):\n"
            f"{refund_line}Recent charges:\n{charges}"
        )

    impact = context.get("impact")
    if impact is not None and impact.matched:
        sections.append(
            f"Known technical incident {impact.incident_id} ({impact.status}): "
            f"{impact.title}\n{impact.description}"
        )

    access = context.get("access")
    if access is not None and access.matched:
        sections.append(
            f"Account access status: {'LOCKED' if access.locked else 'not locked'}, "
            f"failed login attempts: {access.failed_login_attempts}, "
            f"MFA enabled: {access.mfa_enabled}."
        )

    if not sections:
        return "No supporting information was found."
    return "\n\n".join(sections)
