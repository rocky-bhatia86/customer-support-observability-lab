#!/usr/bin/env python3
"""Summarize real Langfuse trace/observation data for recent workflow runs.

This reads back what was actually recorded by scripts/run_ticket.py and
scripts/run_batch.py via the Langfuse REST API -- it does not compute or
guess anything from local state, and it does not fabricate a number when
Langfuse hasn't recorded one (e.g. cost is left as "n/a" rather than 0.00
if no model pricing is configured; see README "Cost tracking limitations").

Note: Langfuse ingestion is asynchronous. If you just ran a batch, wait
15-30 seconds before running this script, or it may see partial data.

Usage:
    python scripts/analyze_traces.py
    python scripts/analyze_traces.py --since-minutes 120 --limit 200
"""
import argparse
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langfuse import get_client
from langfuse.api.commons.errors.unauthorized_error import UnauthorizedError

from support_ai.config import load_config

_WORKFLOW_TRACE_NAME = "support_ticket_workflow"


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) < 5:
        return None  # not enough data for a meaningful p95
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since-minutes", type=int, default=120)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    load_config()  # loads .env so LANGFUSE_* / OPENAI_* are in os.environ
    client = get_client()

    try:
        since = datetime.now(timezone.utc) - timedelta(minutes=args.since_minutes)
        traces_page = client.api.trace.list(
            name=_WORKFLOW_TRACE_NAME,
            from_timestamp=since,
            limit=args.limit,
        )
    except AttributeError:
        raise SystemExit(
            "Langfuse client is not initialized -- set LANGFUSE_PUBLIC_KEY, "
            "LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in .env before running "
            "this script (see README 'Langfuse setup')."
        )
    except UnauthorizedError:
        raise SystemExit(
            "Langfuse rejected these credentials (401) -- double-check "
            "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in "
            ".env match a real project."
        )
    traces = traces_page.data

    if not traces:
        print(
            f"No '{_WORKFLOW_TRACE_NAME}' traces found in the last "
            f"{args.since_minutes} minutes. Run scripts/run_batch.py first, "
            "wait ~30s for ingestion, then retry."
        )
        return

    latencies = [t.latency for t in traces if t.latency is not None]
    iterations = [
        t.metadata.get("iterations") for t in traces
        if t.metadata and t.metadata.get("iterations") is not None
    ]
    costs = [t.total_cost for t in traces if t.total_cost is not None and t.total_cost > 0]

    generation_counts = []
    retrieval_counts = []
    retry_ticket_count = 0
    loop_ticket_count = 0  # more than one iteration
    total_input_tokens = 0
    total_output_tokens = 0
    tickets_with_token_data = 0

    for trace in traces:
        observations = client.api.observations.get_many(trace_id=trace.id).data

        generations = [o for o in observations if o.type == "GENERATION"]
        retrievers = [o for o in observations if o.type == "RETRIEVER"]
        tool_spans = [o for o in observations if o.type == "TOOL"]

        generation_counts.append(len(generations))
        retrieval_counts.append(len(retrievers))

        if any(o.level == "ERROR" for o in tool_spans):
            retry_ticket_count += 1

        iteration_count = trace.metadata.get("iterations") if trace.metadata else None
        if iteration_count and iteration_count > 1:
            loop_ticket_count += 1

        ticket_had_usage = False
        for gen in generations:
            usage = gen.usage_details or {}
            if usage:
                ticket_had_usage = True
                total_input_tokens += usage.get("input", 0)
                total_output_tokens += usage.get("output", 0)
        if ticket_had_usage:
            tickets_with_token_data += 1

    n = len(traces)
    p95_latency = _percentile(latencies, 95)

    print(f"Tickets processed:            {n}")
    print(f"Average latency (s):          {statistics.mean(latencies):.2f}" if latencies else "Average latency (s):          n/a")
    print(f"P95 latency (s):               {p95_latency:.2f}" if p95_latency is not None else "P95 latency (s):               n/a (need 5+ traces)")
    print(f"Average iterations/ticket:    {statistics.mean(iterations):.2f}" if iterations else "Average iterations/ticket:    n/a")
    print(f"Average LLM calls/ticket:     {statistics.mean(generation_counts):.2f}" if generation_counts else "Average LLM calls/ticket:     n/a")
    print(f"Average KB retrievals/ticket: {statistics.mean(retrieval_counts):.2f}" if retrieval_counts else "Average KB retrievals/ticket: n/a")
    print(f"Retry rate:                   {retry_ticket_count}/{n} tickets ({100 * retry_ticket_count / n:.0f}%)")
    print(f"Loop rate (>1 iteration):     {loop_ticket_count}/{n} tickets ({100 * loop_ticket_count / n:.0f}%)")

    if tickets_with_token_data:
        print(f"Total input tokens:           {total_input_tokens}")
        print(f"Total output tokens:          {total_output_tokens}")
    else:
        print("Total input/output tokens:    n/a (no generation usage_details recorded)")

    if costs:
        print(f"Estimated total cost (USD):   {sum(costs):.4f}")
    else:
        print(
            "Estimated total cost (USD):   n/a -- Langfuse has no pricing "
            f"entry for model '{load_config().model_name}'. Token counts above "
            "are real; cost requires registering this model's pricing in "
            "your Langfuse project (see README 'Cost tracking limitations')."
        )


if __name__ == "__main__":
    main()
