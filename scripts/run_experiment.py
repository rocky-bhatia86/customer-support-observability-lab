#!/usr/bin/env python3
"""Runs the "support-tickets-eval" Langfuse Dataset through the real
workflow using langfuse.run_experiment(), which handles tracing, per-item
LLM-as-a-judge scoring, and run-level aggregates natively -- replacing the
hand-rolled loop in scripts/run_eval.py + the printed table in
scripts/analyze_evals.py with Langfuse's own Experiments UI (native
run-to-run comparison, no code needed to see trends).

Run this repeatedly (e.g. under v1, then v2) and compare the resulting
runs directly in Langfuse: Datasets -> support-tickets-eval -> Runs.

Usage:
    python scripts/run_experiment.py --checker-version v1
    python scripts/run_experiment.py --checker-version v2
"""
import argparse
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse

from support_ai.config import load_config
from support_ai.judge import LLMJudge
from support_ai.models import Ticket
from support_ai.workflow import WorkflowRunner

_DATASET_NAME = "support-tickets-eval"
_SCORE_DIMENSIONS = ("correctness", "groundedness", "helpfulness", "policy_adherence")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checker-version", choices=["v1", "v2"], default=None)
    args = parser.parse_args()

    base_config = load_config()
    version = args.checker_version or base_config.checker_prompt_version
    config = dataclasses.replace(base_config, checker_prompt_version=version)

    runner = WorkflowRunner(config)
    judge = LLMJudge(config)

    def task(*, item, **kwargs):
        ticket = Ticket(
            id=item.input["ticket_id"],
            text=item.input["text"],
            account_id=item.input.get("account_id"),
        )
        result = runner.run(ticket)
        return {
            "final_response": result.final_response,
            "status": result.status,
            "iterations": result.iterations,
            "context": result.context,
        }

    def make_score_evaluator(dimension: str):
        def evaluator(*, input, output, expected_output=None, metadata=None, **kwargs):
            notes = (metadata or {}).get("notes", "")
            ticket = Ticket(id=input["ticket_id"], text=input["text"], account_id=input.get("account_id"))
            scores = judge.evaluate(ticket, output["context"], output["final_response"], output["status"], notes)
            return {"name": dimension, "value": getattr(scores, dimension)}
        evaluator.__name__ = f"{dimension}_evaluator"
        return evaluator

    def overall_evaluator(*, input, output, expected_output=None, metadata=None, **kwargs):
        notes = (metadata or {}).get("notes", "")
        ticket = Ticket(id=input["ticket_id"], text=input["text"], account_id=input.get("account_id"))
        scores = judge.evaluate(ticket, output["context"], output["final_response"], output["status"], notes)
        return {"name": "overall", "value": scores.overall, "comment": scores.reasoning}

    lf = Langfuse()
    dataset = lf.get_dataset(_DATASET_NAME)

    result = lf.run_experiment(
        name=f"checker-{version}",
        description=f"Full ticket set under CHECKER_PROMPT_VERSION={version}",
        data=dataset.items,
        task=task,
        evaluators=[make_score_evaluator(d) for d in _SCORE_DIMENSIONS] + [overall_evaluator],
        metadata={"checker_prompt_version": version},
        max_concurrency=1,  # keep it sequential -- shared local rate limits, easier to read output
    )

    print(f"Run name: {result.run_name}")
    if result.dataset_run_url:
        print(f"View in Langfuse: {result.dataset_run_url}")
    for item_result in result.item_results:
        outcome = item_result.output["status"] if item_result.output else "ERROR"
        print(f"  {item_result.item.input['ticket_id']}: {outcome}")


if __name__ == "__main__":
    main()
