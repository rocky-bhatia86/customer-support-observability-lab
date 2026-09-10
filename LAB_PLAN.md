# LAB_PLAN.md — Stop Guessing, Start Measuring

This file documents the baseline, the controlled production-failure branch,
and the Langfuse observability stage layered on top of it. It intentionally
stops before evaluation datasets or LLM-as-a-judge are added.

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
branch (and carried forward here). The orchestrator no longer just
classifies a ticket — it also decides a **plan**: which of the specialist
agents below are actually needed for that specific ticket. Not every
ticket runs the same agents.

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

## Observability (`langfuse-observability`, tag `observability-v1`)

Branched from `failure-scenarios`. No agent logic, prompts, routing, or
failure behavior was changed -- the only additions are Langfuse tracing
calls, so this branch demonstrates the *same* system, now instrumented.

**What was added:**

- `langfuse` pinned as a dependency (`pyproject.toml`); `LANGFUSE_PUBLIC_KEY`
  / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` added to `.env.example` (blank by
  default -- tracing safely no-ops without them).
- `support_ai.llm_client.call_llm` (the single LLM chokepoint) is wrapped as
  a Langfuse "generation" observation, recording model, input, output,
  latency (automatic), real token usage from the OpenAI response, model
  parameters (temperature), and a `version` tag (the checker passes
  `CHECKER_PROMPT_VERSION` through it).
- `WorkflowRunner.run` is wrapped as the root trace `support_ticket_workflow`,
  carrying ticket id, category, model name, checker prompt version, final
  status, and total duration as trace metadata.
- Each retry loop iteration is wrapped in its own `iteration_N` span, so a
  looping ticket visibly shows N repeated
  `kb_retrieval -> drafter -> quality_checker` cycles under the trace.
- `OrchestratorAgent.classify`, `KBRetrievalAgent.retrieve`,
  `DrafterAgent.draft`, and `QualityCheckerAgent.check` are each their own
  span/observation (types: agent, retriever, agent, agent respectively);
  `tools.kb_search.search` is its own "tool" span nested under retrieval, so
  Failure C's failed-then-retried call shows up as two sibling tool spans.
- The checker's span additionally records verdict, rejection reason,
  iteration number, and prompt version.
- `scripts/analyze_traces.py` reads back real Langfuse data (via
  `client.api.trace.list` / `client.api.observations.get_many`) for recent
  `support_ticket_workflow` traces and reports: tickets processed, average
  and p95 latency, average iterations/ticket, average LLM calls/ticket,
  average KB retrievals/ticket, retry rate, loop rate, total input/output
  tokens, and estimated total cost (or an explicit "n/a" with the reason,
  never a fabricated number -- see README "Cost tracking limitations").

**Observability questions this stage can now answer, from real trace data
instead of guesswork:**

- Which agent is slow? (per-span latency in the trace tree)
- How many LLM calls happen per ticket? (`GENERATION` observation count)
- How many KB retrievals happen? (`RETRIEVER` observation count)
- Where do retries occur? (`TOOL` spans with an `ERROR` level, always paired
  with a successful sibling)
- Which tickets cause loops? (traces with `metadata.iterations > 1`)
- How many iterations happen? (`iteration_N` span count / trace metadata)
- How many tokens are consumed? (`usage_details` on each generation)
- What is the estimated model cost? (Langfuse-computed `total_cost`, when
  the model is registered with pricing)
- Which model/prompt version ran? (trace/generation `model` and `version`
  fields)
- Did the model/prompt change alter behavior? (compare `v1` vs `v2` batches
  by `metadata.checker_prompt_version`)
- What is the quality of the final response? -- **not yet answered**; this
  requires the evaluation dataset and LLM-as-a-judge stage, still to come.

See README.md "Langfuse setup" for how to inspect a trace and identify each
of the four failures directly in the Langfuse UI.

## Explicitly out of scope for this stage

No evaluation dataset population, no LLM-as-a-judge, no dashboard beyond
`scripts/analyze_traces.py`'s text summary. `data/eval_dataset.json` still
exists only as an empty placeholder -- it is populated in the next stage.
