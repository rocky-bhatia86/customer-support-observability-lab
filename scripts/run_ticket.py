#!/usr/bin/env python3
"""Run a single ticket through the workflow.

Usage:
    python scripts/run_ticket.py TCK-001
    python scripts/run_ticket.py --text "How do I reset my password?"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langfuse import get_client

from support_ai.config import load_config
from support_ai.models import Ticket
from support_ai.workflow import WorkflowRunner

_TICKETS_PATH = Path(__file__).resolve().parents[1] / "data" / "tickets.json"


def _print_result(result):
    print(f"Ticket ID:            {result.ticket_id}")
    print(f"Category:             {result.category}")
    print(f"Final status:         {result.status}")
    print(f"Final response:       {result.final_response}")
    print(f"Total workflow time:  {result.elapsed_seconds:.2f}s")
    print(f"Workflow iterations:  {result.iterations}")
    print(f"Prompt/completion tok:{result.total_prompt_tokens}/{result.total_completion_tokens}")
    print("Trace:")
    for step in result.steps:
        print(
            f"  [iter {step.iteration}] {step.agent}.{step.action} "
            f"({step.elapsed_seconds:.2f}s) {step.detail}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_id", nargs="?", help="Ticket id from data/tickets.json")
    parser.add_argument("--text", help="Raw ticket text instead of a ticket id")
    args = parser.parse_args()

    if args.text:
        ticket = Ticket(id="ADHOC-1", text=args.text)
    elif args.ticket_id:
        tickets = json.loads(_TICKETS_PATH.read_text())
        match = next((t for t in tickets if t["id"] == args.ticket_id), None)
        if not match:
            raise SystemExit(f"No ticket with id {args.ticket_id} in {_TICKETS_PATH}")
        ticket = Ticket(**match)
    else:
        raise SystemExit("Provide a ticket_id or --text")

    config = load_config()
    runner = WorkflowRunner(config)
    try:
        result = runner.run(ticket)
        _print_result(result)
    finally:
        # Langfuse exports spans on a background thread/interval; flush
        # here so a short-lived CLI run doesn't exit before delivery.
        get_client().flush()


if __name__ == "__main__":
    main()
