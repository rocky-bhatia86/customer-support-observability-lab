"""MCP server exposing this lab's 4 lookup tools over the Model Context
Protocol, so any MCP-speaking client (this app, or an external one like
Claude Desktop) can call them -- not just this app's own agents.

Each tool wraps the exact same lookup logic the agents already use
(same JSON files, same matching rules) so results are identical whether
called directly (as the agents still do) or via MCP.

Run standalone for manual testing:
    python -m support_ai.mcp_server
Normally launched as a subprocess by support_ai.mcp_client.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logging.getLogger("mcp").setLevel(logging.WARNING)

_ROOT = Path(__file__).resolve().parents[2]
_KB_PATH = _ROOT / "kb" / "articles.json"
_ACCOUNTS_PATH = _ROOT / "data" / "accounts.json"
_INCIDENTS_PATH = _ROOT / "data" / "incidents.json"
_ACCESS_PATH = _ROOT / "data" / "access_records.json"

_STOPWORDS = {
    "a", "an", "the", "is", "was", "were", "i", "my", "me", "to", "for",
    "of", "on", "in", "and", "or", "it", "this", "that", "how", "do", "does",
}

mcp = FastMCP("support-ai-tools")


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS}


@mcp.tool()
def search_knowledge_base(category: str, query: str) -> dict:
    """Search the help-center knowledge base for articles relevant to a
    customer query within a given category (billing, bug, or how-to).
    Returns up to 3 matched articles ranked by keyword overlap."""
    articles = json.loads(_KB_PATH.read_text())
    query_tokens = _tokenize(query)

    candidates = [a for a in articles if a["category"] == category] or articles
    scored = []
    for article in candidates:
        article_tokens = _tokenize(article["title"] + " " + article["content"])
        scored.append((len(query_tokens & article_tokens), article))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    top = candidates[:3] if scored and scored[0][0] == 0 else [a for _, a in scored[:3]]
    return {"matched_ids": [a["id"] for a in top], "articles": top}


@mcp.tool()
def lookup_account_data(account_id: str) -> dict:
    """Look up a customer account's billing/subscription record: plan,
    subscription status, recent charges, and refund eligibility window."""
    accounts = {a["account_id"]: a for a in json.loads(_ACCOUNTS_PATH.read_text())}
    record = accounts.get(account_id)
    if not record:
        return {"matched": False}
    return {
        "matched": True,
        "account_id": record["account_id"],
        "plan": record["plan"],
        "subscription_status": record["subscription_status"],
        "recent_charges": record["recent_charges"],
        "refund_eligible_days": record.get("refund_eligible_days"),
    }


@mcp.tool()
def check_known_incidents(query: str) -> dict:
    """Check whether a customer's issue matches a known/active technical
    incident, by keyword overlap against the incident log."""
    incidents = json.loads(_INCIDENTS_PATH.read_text())
    query_tokens = _tokenize(query)

    best, best_overlap = None, 0
    for incident in incidents:
        overlap = len(query_tokens & set(incident["keywords"]))
        if overlap > best_overlap:
            best_overlap, best = overlap, incident

    if not best:
        return {"matched": False}
    return {
        "matched": True,
        "incident_id": best["incident_id"],
        "title": best["title"],
        "status": best["status"],
        "description": best["description"],
    }


@mcp.tool()
def check_account_access(account_id: str) -> dict:
    """Look up a customer account's login/lockout status: whether it's
    locked, recent failed login attempts, and MFA status."""
    records = {r["account_id"]: r for r in json.loads(_ACCESS_PATH.read_text())}
    record = records.get(account_id)
    if not record:
        return {"matched": False}
    return {
        "matched": True,
        "account_id": record["account_id"],
        "locked": record["locked"],
        "failed_login_attempts": record["failed_login_attempts"],
        "mfa_enabled": record["mfa_enabled"],
        "last_login": record.get("last_login"),
    }


if __name__ == "__main__":
    mcp.run()
