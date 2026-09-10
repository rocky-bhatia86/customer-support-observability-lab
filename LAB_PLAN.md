# LAB_PLAN.md — Stop Guessing, Start Measuring

This file documents the baseline (`main`), the controlled production
failures and MCP tool-calling layered on it, and the Langfuse observability
stage layered on top of that. It intentionally stops before evaluation
datasets or LLM-as-a-judge are added.

## Base pipeline

What works:

- `OrchestratorAgent` classifies each ticket into `billing`, `bug`, or
  `how-to`, and decides a **plan**: which specialist agents this specific
  ticket actually needs. Not every ticket runs the same agents.
- Specialist agents, run only when the plan calls for them:
  - `KBRetrievalAgent` — keyword-overlap search against `kb/articles.json`.
  - `AccountDataAgent` — simulated billing/subscription lookup.
  - `ImpactDiagnosticsAgent` — simulated known-incident matching.
  - `AccountAccessAgent` — simulated login/lockout status lookup.
- `DrafterAgent` writes a reply grounded only in whatever combination of the
  above was gathered.
- `QualityCheckerAgent` (prompt version `v1`, reasonable standard) accepts a
  draft that is relevant, grounded, and addresses the main question, even if
  a minor detail is phrased generally rather than as an exact figure.
- `WorkflowRunner` loops plan -> draft -> check up to `MAX_AGENT_ITERATIONS`
  (default 5), and returns `RESOLVED` or `ESCALATED_MAX_ITERATIONS`.

A real Flask API + chat UI (`scripts/run_server.py`, `web/index.html`) runs
this system live: real LLM calls, a live SSE stream of each agent step as
it happens, and a live `v1`/`v2` checker toggle for demonstrating Failure D
without restarting the server. See `SETUP.md` for how to run it.

## MCP tool-calling

Every specialist agent's data lookup (`AccountDataAgent.lookup`,
`ImpactDiagnosticsAgent.check`, `AccountAccessAgent.check`, and the real
(non-simulated) path of `KBRetrievalAgent.retrieve`) goes through the
**Model Context Protocol** instead of a direct function call:

- `support_ai.mcp_server` is a standalone `FastMCP` server exposing 4 tools
  (`lookup_account_data`, `check_known_incidents`, `check_account_access`,
  `search_knowledge_base`), each wrapping the exact same lookup logic and
  JSON files the agents always used — results are identical, only the call
  path changed. Run it standalone with `python -m support_ai.mcp_server`,
  or point any other MCP client (Claude Desktop, an IDE, etc.) at it.
- `support_ai.mcp_client` is the sync/async bridge the agents use: a
  dedicated background thread runs one persistent asyncio driver holding
  the MCP stdio session open for the process lifetime, fed via a queue, so
  sync agent code can call `call_tool(name, arguments)` and block for a
  real result. Cold start (subprocess spawn + handshake) is a few hundred
  milliseconds; every call after that is sub-millisecond.
- The Failure C error-simulation path (below) stays local rather than going
  through MCP, since `simulate_error` is an internal test hook, not
  something that belongs on a tool schema a real MCP client would see.

## Production failures

Four controlled, reproducible failures are layered on top of the base
pipeline above. All four apply regardless of which specialist agents a
given ticket's plan calls for.

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
`WorkflowRunner`'s retry path accumulates every previously retrieved article
into a growing list instead of replacing it with a fresh retrieval each
iteration. The final answer still reads fine — the only symptom is that
prompt tokens sent to the Drafter and Checker grow with each retry, which is
invisible without instrumentation.

### C — Retrieval error + retry
`TCK-002` (the API timeout ticket) deterministically raises `KBSearchError`
on its first retrieval call; `KBRetrievalAgent` catches it and retries once
(via MCP), which succeeds. The final response is unaffected, but the retry
is now part of the trace.

### D — Model / prompt regression
`CHECKER_PROMPT_VERSION` toggles between `v1` (baseline standard) and `v2`
(strict: every question must be answered, exact figures required when asked
for, and each claim must cite a KB article id). `v1` is the default here —
start here so the system looks and behaves normally — but flipping to `v2`
live from the chat UI's checker toggle (no restart needed) simulates "last
week's model/prompt bump" on the identical code. This is the same-branch
before/after lever: run `scripts/run_batch.py` once with each value and diff
the output.

## Observability (`langfuse-observability`, tag `observability-v1`)

Branched from `main`. No agent logic, prompts, routing, failure, or MCP
tool-calling behavior was changed -- the only additions are Langfuse
tracing calls, so this branch demonstrates the *same* system, now
instrumented.

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
  each specialist agent's MCP-routed lookup (`account_data.lookup`,
  `impact_diagnostics.check`, `account_access.check`) is its own "tool"
  span, as is `tools.kb_search.search`'s local error-simulation call --
  Failure C's failed-then-retried call shows up as two sibling tool spans.
- The checker's span additionally records verdict, rejection reason,
  iteration number, and prompt version.
- `scripts/analyze_traces.py` reads back real Langfuse data (via the
  Observations v2 API, `client.api.observations.get_many(..., fields=...)`
  -- the deprecated `client.api.trace.list` is disabled on self-hosted
  Langfuse v4's default "events_only" write mode) for recent
  `support_ticket_workflow` traces and reports: tickets processed, average
  and p95 latency, average iterations/ticket, average LLM calls/ticket,
  average KB retrievals/ticket, retry rate, loop rate, total input/output
  tokens, and estimated total cost (or an explicit "n/a" with the reason,
  never a fabricated number -- see README "Cost tracking").

**Observability questions this stage can now answer, from real trace data
instead of guesswork:**

- Which agent is slow? (per-span latency in the trace tree)
- How many LLM calls happen per ticket? (`GENERATION` observation count)
- How many MCP tool calls happen? (`TOOL` observation count per specialist
  agent span)
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
