#!/usr/bin/env python3
"""Run the full data/tickets.json dataset through the workflow and print a
comparable summary table (baseline vs failure-scenarios branches use the
same runner and the same input file)."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", help="Optional path to also write results as JSON")
    args = parser.parse_args()

    tickets = [Ticket(**item) for item in json.loads(_TICKETS_PATH.read_text())]
    config = load_config()
    runner = WorkflowRunner(config)

    header = f"{'ticket_id':<10} {'category':<9} {'status':<26} {'iters':<6} {'elapsed_s':<10}"
    print(header)
    print("-" * len(header))

    results = []
    for ticket in tickets:
        result = runner.run(ticket)
        print(
            f"{result.ticket_id:<10} {result.category:<9} {result.status:<26} "
            f"{result.iterations:<6} {result.elapsed_seconds:<10.2f}"
        )
        print(f"  -> {result.final_response}")
        results.append(result)

    # Langfuse exports spans on a background thread/interval; flush here so
    # a short-lived batch run doesn't exit before all traces are delivered.
    get_client().flush()

    if args.output_json:
        payload = [
            {
                "ticket_id": r.ticket_id,
                "category": r.category,
                "status": r.status,
                "final_response": r.final_response,
                "iterations": r.iterations,
                "elapsed_seconds": r.elapsed_seconds,
                "prompt_tokens": r.total_prompt_tokens,
                "completion_tokens": r.total_completion_tokens,
                "steps": [step.__dict__ for step in r.steps],
            }
            for r in results
        ]
        Path(args.output_json).write_text(json.dumps(payload, indent=2))
        print(f"\nWrote {len(payload)} results to {args.output_json}")


if __name__ == "__main__":
    main()
