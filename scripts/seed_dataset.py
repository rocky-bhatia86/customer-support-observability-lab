#!/usr/bin/env python3
"""Seeds (or re-syncs) the "support-tickets-eval" Langfuse Dataset from
data/tickets.json + data/eval_dataset.json's per-ticket notes.

Safe to re-run: each item's id is derived from the ticket id, so re-running
updates the existing item rather than creating duplicates.

Usage:
    python scripts/seed_dataset.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse

_ROOT = Path(__file__).resolve().parents[1]
_TICKETS_PATH = _ROOT / "data" / "tickets.json"
_EVAL_DATASET_PATH = _ROOT / "data" / "eval_dataset.json"
_DATASET_NAME = "support-tickets-eval"


def main():
    lf = Langfuse()
    lf.create_dataset(name=_DATASET_NAME, description="The 6 support tickets used across this lab's stages.")

    tickets = json.loads(_TICKETS_PATH.read_text())
    notes_by_id = {e["ticket_id"]: e["notes"] for e in json.loads(_EVAL_DATASET_PATH.read_text())}

    for ticket in tickets:
        lf.create_dataset_item(
            id=f"ticket-{ticket['id']}",
            dataset_name=_DATASET_NAME,
            input={"ticket_id": ticket["id"], "text": ticket["text"], "account_id": ticket.get("account_id")},
            expected_output=None,
            metadata={"notes": notes_by_id.get(ticket["id"], "")},
        )
        print(f"Seeded dataset item for {ticket['id']}")

    lf.flush()
    print(f"\nDataset '{_DATASET_NAME}' now has {len(tickets)} item(s).")


if __name__ == "__main__":
    main()
