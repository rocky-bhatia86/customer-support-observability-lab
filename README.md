# Support AI Lab

### Stop Guessing, Start Measuring

[![Tests](https://github.com/rocky-bhatia86/customer-support-observability-lab/actions/workflows/tests.yml/badge.svg?branch=langfuse-observability)](https://github.com/rocky-bhatia86/customer-support-observability-lab/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

A hands-on lab for AI observability: a real multi-agent customer support
system, with real MCP tool-calling, real production failure modes, and now
real Langfuse tracing layered on top — staged across branches so each
capability can be studied in isolation. (LLM-as-a-judge evaluation is the
next stage, on `llm-judge-eval` — not yet on this branch.)

Ask it something in the chat UI and watch a live orchestrator dynamically
route your ticket through whichever of 7 specialist agents it actually
needs. Each specialist agent looks up its data by calling a tool exposed
over the **Model Context Protocol (MCP)** — the same tool server any other
MCP client (Claude Desktop, an IDE, etc.) could call — then the ticket
iterates against a quality gate until it resolves or escalates, exactly
like a production agentic system would, with every step traced.

## Quickstart

```bash
git checkout langfuse-observability
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env                # set OPENAI_API_KEY
python scripts/run_server.py
```

Open **http://localhost:8000** — this works with tracing fully disabled
(all three `LANGFUSE_*` variables blank). To turn tracing on, see
"Langfuse setup" below.

**Full step-by-step instructions across every stage are in
[`SETUP.md`](SETUP.md).** The design rationale and the story behind each
production failure are in [`LAB_PLAN.md`](LAB_PLAN.md).

## Branches

Each branch adds exactly one capability on top of the previous one:

| Branch | Adds |
|---|---|
| `main` | The full dynamic multi-agent system: MCP-based tool calling, a real chat UI, and 4 controlled production failures |
| `langfuse-observability` (this branch) | Real tracing (Langfuse), layered on the same code |
| `llm-judge-eval` | LLM-as-a-judge evaluation, Langfuse Prompt Management, and Datasets/Experiments |

Start at `main` — it already includes the full agent system and failure
scenarios, so every later branch builds on a complete, working base.

## Architecture

```
Ticket -> Orchestrator (classify + pick agent plan)
              |
              v
   dynamically runs whichever of:
     Knowledge Agent, Account/Billing Agent,
     Impact/Diagnostics Agent, Account Access Agent
   the plan calls for -- each one calls its data lookup
   as an MCP tool (support_ai.mcp_server), not a direct
   function call
              |
              v
        Drafter -> Quality Checker
              ^            |
              +-- REJECT_AND_RETRIEVE --+
                (up to 5 iterations)
```

Not every ticket runs the same agents — the orchestrator's classification
call decides the plan per ticket. Every LLM call goes through the single
`support_ai.llm_client.call_llm` function — the one seam instrumented as a
Langfuse "generation" on this branch. Every tool lookup goes through
`support_ai.mcp_client.call_tool`, which talks to the standalone MCP server
in `support_ai.mcp_server` over stdio — the same 4 tools would work
unchanged from any other MCP client.

## Testing

```bash
pytest -q
```

Tests never call a real LLM — `call_llm` is monkeypatched, so `pytest` runs
without network access or an API key. Langfuse tracing is also safe to
leave disabled during tests. The MCP server subprocess does start for real
during tests (tool lookups are not mocked), which is why the first test run
is slightly slower than later ones. This is also why CI needs no secrets.

## License

[MIT](LICENSE)

## Langfuse setup

This branch adds the `langfuse` SDK (pinned in `pyproject.toml`) as the
tracing backend. It's off by default: with all three `LANGFUSE_*` variables
blank, the SDK disables span creation and the workflow runs exactly as
before. You may still see a single harmless stderr line at process exit
(`Failed to export span batch...`) from the SDK's background flush thread —
this is a cosmetic SDK quirk with no credentials configured, not a
functional issue; it does not affect test results or the workflow's output.

To turn tracing on:

1. **Cloud** (fastest): sign up at https://cloud.langfuse.com (or the EU
   region), create a project, and copy its Public/Secret keys.
2. **Self-hosted**: run the Langfuse docker compose stack, e.g.:
   ```bash
   git clone https://github.com/langfuse/langfuse.git
   cd langfuse && docker compose up -d
   ```
   Then open http://localhost:3000, create a project, and copy its keys.
3. Set in `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com   # or http://localhost:3000
   ```

No credentials are ever hard-coded in this repo — they only ever come from
`.env` (gitignored) or your shell environment.

### Running the same batch with tracing on

```bash
python scripts/run_batch.py
# wait ~15-30s for Langfuse ingestion (it's async), then:
python scripts/analyze_traces.py
```

### How to inspect a trace

Open your Langfuse project -> Tracing. Each ticket produces one trace named
`support_ticket_workflow`. Click a trace to see the full tree:

```
support_ticket_workflow (trace: ticket id, category, model, checker version, status, duration)
├── orchestrator.classify (agent)
│   └── llm_call (generation: model, input, output, tokens)
├── iteration_1 (span)
│   ├── kb_retrieval.retrieve (retriever: query, matched KB ids)
│   │   └── kb_search.search (tool: category/query in, matched ids + count out)
│   ├── drafter.draft (agent)
│   │   └── llm_call (generation)
│   └── quality_checker.check (agent: verdict, reason, iteration, prompt version)
│       └── llm_call (generation)
├── iteration_2 (span)        # only present on retry
│   └── ... same shape as iteration_1
```

### How to identify the loop (Failure A)

Open a trace for `TCK-005` (or any ticket that didn't resolve on iteration
1). You'll see multiple `iteration_N` spans, each containing its own
`kb_retrieval -> drafter -> quality_checker` cycle. The trace's top-level
`status` metadata reads `ESCALATED_MAX_ITERATIONS` once it hits
`iteration_5` without an ACCEPT. Filter traces by
`metadata.iterations > 1` (or use `scripts/analyze_traces.py`'s "loop rate")
to find every ticket that looped, not just this one.

### How to identify token growth (Failure B)

Open the same looping trace and compare the `drafter.draft -> llm_call`
generation's input size/prompt tokens across `iteration_1`, `iteration_2`,
... The input grows every iteration because retrieved KB articles are
accumulated rather than replaced -- visible directly in each generation's
recorded `input` and `usage_details.input` token count.

### How to identify retries (Failure C)

Open the trace for `TCK-002`. Inside `iteration_1 -> kb_retrieval.retrieve`
there are two sibling `kb_search.search` tool spans: the first is marked
as an error (level `ERROR`, exception `KBSearchError`), the second
succeeds. `scripts/analyze_traces.py` reports this as "retry rate".

### How to compare model/prompt versions (Failure D)

Run the batch twice, once per checker version, then compare:

```bash
CHECKER_PROMPT_VERSION=v2 python scripts/run_batch.py
CHECKER_PROMPT_VERSION=v1 python scripts/run_batch.py
```

In Langfuse, filter/group traces by `metadata.checker_prompt_version` (or
by the `version` field on each `quality_checker.check -> llm_call`
generation). You should see materially more `REJECT_AND_RETRIEVE`
verdicts, more iterations, and higher token usage under `v2` for the same
ticket set -- this is the "last week's model bump changed behavior,
now proven with data" scenario.

### Cost tracking

Every `llm_call` generation records real `usage_details` (`input`/`output`/
`total` tokens) taken directly from the OpenAI response -- these are never
estimated or invented. Langfuse computes **cost** server-side by matching
the generation's `model` name against a pricing table configured in your
Langfuse project. Common OpenAI models -- including `gpt-4o-mini`, this
lab's default -- already have default pricing in both Langfuse Cloud and
self-hosted deployments, so cost is computed automatically with zero setup;
`scripts/analyze_traces.py` reports it as a real dollar figure, not an
estimate. If you point `MODEL_NAME` at a custom/self-hosted model name that
Langfuse doesn't recognize, cost will show as unavailable until you add
that model's real per-token pricing under Project Settings -> Models in the
Langfuse UI. This lab does not hard-code or guess any per-token price in
application code.

### Langfuse v4 events_only mode

Self-hosted Langfuse v4 deployments run in "events_only" write mode by
default, which disables the legacy `GET /api/public/traces` and
`GET /api/public/observations` (v1) query endpoints entirely --
`scripts/analyze_traces.py` uses the Observations v2 API
(`client.api.observations.get_many(..., fields=...)`, backed by
`GET /api/public/v2/observations`) instead, which works on both events_only
and legacy-write deployments. If you fork this script to query traces/cost
data yourself, use the v2 observations client, not `client.api.trace.list`.
