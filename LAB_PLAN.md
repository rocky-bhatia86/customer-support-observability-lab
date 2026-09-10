# LAB_PLAN.md — Stop Guessing, Start Measuring

This file documents Stages 0-12: the clean baseline and the controlled
production-failure branch. It intentionally stops before any observability
tooling is added.

## Baseline (`main`, tag `baseline-v1`)

What works:

- `OrchestratorAgent` classifies each ticket into `billing`, `bug`, or `how-to`.
- `KBRetrievalAgent` does a fresh, deterministic keyword-overlap search against
  `kb/articles.json` every iteration.
- `DrafterAgent` writes a reply grounded only in the retrieved articles.
- `QualityCheckerAgent` (prompt version `v1`, reasonable standard) accepts a
  draft that is relevant, grounded, and addresses the main question, even if
  a minor detail is phrased generally rather than as an exact figure.
- `WorkflowRunner` loops retrieve -> draft -> check up to `MAX_AGENT_ITERATIONS`
  (default 5), and returns `RESOLVED` or `ESCALATED_MAX_ITERATIONS`.

What you can observe by running `scripts/run_batch.py`: for all 5 tickets,
including the ambiguous one (`TCK-005`), the checker accepts within 1-2
iterations under `CHECKER_PROMPT_VERSION=v1`. This is the "everything looks
fine" state the rest of the lab uses as a reference point.

## Production problems (`failure-scenarios`, tag `failures-v1`)

Four controlled, reproducible failures are layered on top of the identical
baseline code. Nothing on `main` is modified after `baseline-v1`.

### A — Checker loop
`TCK-005` asks for the *exact* number of business days until a refund. No KB
article states an exact number (`KB-002` deliberately says "a few business
days"). Under the stricter `CHECKER_PROMPT_VERSION=v2` (see Failure D), the
checker's rule "an exact figure must be provided when the customer asks for
one" can never be satisfied by the KB content as written, so the draft is
rejected every iteration until the workflow hits `MAX_AGENT_ITERATIONS` and
returns `ESCALATED_MAX_ITERATIONS`. The process still terminates — it is a
controlled outcome, not a hang.

### B — Token / context bloat
On `failure-scenarios`, `WorkflowRunner`'s retry path accumulates every
previously retrieved article into a growing list instead of replacing it
with a fresh retrieval each iteration (baseline behavior). The final answer
still reads fine — the only symptom is that prompt tokens sent to the
Drafter and Checker grow with each retry, which is invisible without
instrumentation.

### C — Retrieval error + retry
`TCK-002` (the API timeout ticket) deterministically raises `KBSearchError`
on its first retrieval call; `KBRetrievalAgent` catches it and retries once,
which succeeds. The final response is unaffected, but the retry is now part
of the trace.

### D — Model / prompt regression
`CHECKER_PROMPT_VERSION` toggles between `v1` (baseline standard) and `v2`
(strict: every question must be answered, exact figures required when asked
for, and each claim must cite a KB article id). On `failure-scenarios`, `v2`
is the default — simulating "last week's model/prompt bump" — but setting
`CHECKER_PROMPT_VERSION=v1` via env on the *same* branch reproduces the old,
clean behavior. This is the same-branch before/after lever: run
`scripts/run_batch.py` once with each value and diff the output.

## Addendum: dynamic multi-agent routing + real chat UI

Added after the failure design above, on the same `failure-scenarios`
branch. The orchestrator no longer just classifies a ticket — it also
decides a **plan**: which of the specialist agents below are actually
needed for that specific ticket. Not every ticket runs the same agents.

Specialist agents, run only when the plan calls for them:
- `KBRetrievalAgent` — unchanged from the baseline above.
- `AccountDataAgent` — simulated billing/subscription lookup.
- `ImpactDiagnosticsAgent` — simulated known-incident matching.
- `AccountAccessAgent` — simulated login/lockout status lookup.

`DrafterAgent` and `QualityCheckerAgent` still run every iteration
regardless of the plan, now grounded in whatever combination of the above
was gathered. All four original failures (A–D) still apply unchanged.

A real Flask API + chat UI (`scripts/run_server.py`, `web/index.html`) runs
this system live: real LLM calls, a live SSE stream of each agent step as
it happens, and a live `v1`/`v2` checker toggle for demonstrating Failure D
without restarting the server. See `SETUP.md` for how to run it.

## Observability questions (answered in the NEXT lab stage)

The instrumentation stage must be able to answer, using traces rather than
guesswork:

- Which agent is slow?
- How many LLM calls happen per ticket?
- How many KB retrievals happen?
- Where do retries occur?
- Which tickets cause loops?
- How many iterations happen?
- How many tokens are consumed?
- What is the estimated model cost?
- Which model/prompt version ran?
- Did the model/prompt change alter behavior?
- What is the quality of the final response?

## Explicitly out of scope for this stage

No Langfuse, no tracing SDK, no evaluation framework, no LLM-as-a-judge, no
dashboard. `data/eval_dataset.json` exists as an empty placeholder only —
it is populated in the evaluation stage, not here.
