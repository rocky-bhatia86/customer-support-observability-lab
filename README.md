# Support AI Lab

### Stop Guessing, Start Measuring

[![Tests](https://github.com/rocky-bhatia86/customer-support-observability-lab/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/rocky-bhatia86/customer-support-observability-lab/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

A hands-on lab for AI observability: a real multi-agent customer support
system, with real MCP tool-calling, real production failure modes, real
tracing, and a real LLM-as-a-judge evaluator layered on top — staged across
branches so each capability can be studied in isolation.

Ask it something in the chat UI and watch a live orchestrator dynamically
route your ticket through whichever of 7 specialist agents it actually
needs. Each specialist agent looks up its data by calling a tool exposed
over the **Model Context Protocol (MCP)** — the same tool server any other
MCP client (Claude Desktop, an IDE, etc.) could call — then the ticket
iterates against a quality gate until it resolves or escalates, exactly
like a production agentic system would.

## Quickstart

```bash
git checkout main
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env                # set OPENAI_API_KEY
python scripts/run_server.py
```

Open **http://localhost:8000**. That's the whole setup for the first stage —
no Docker, no external services.

**Full step-by-step instructions, including the observability and
evaluation stages, are in [`SETUP.md`](SETUP.md).** The design rationale and
the story behind each production failure are in [`LAB_PLAN.md`](LAB_PLAN.md).

## Branches

Each branch adds exactly one capability on top of the previous one — nothing
is removed or rewritten along the way:

| Branch | Adds |
|---|---|
| `main` | The full dynamic multi-agent system: MCP-based tool calling, a real chat UI, and 4 controlled production failures |
| `langfuse-observability` | Real tracing (Langfuse), layered on the same code |
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
`support_ai.llm_client.call_llm` function, which is the seam later stages
instrument with Langfuse tracing. Every tool lookup goes through
`support_ai.mcp_client.call_tool`, which talks to the standalone MCP server
in `support_ai.mcp_server` over stdio — the same 4 tools would work
unchanged from any other MCP client.

## Testing

```bash
pytest -q
```

Tests never call a real LLM — `call_llm` is monkeypatched, so `pytest` runs
without network access or an API key. The MCP server subprocess does start
for real during tests (tool lookups are not mocked), which is why the first
test run is slightly slower than later ones. This is also why CI needs no
secrets.

## License

[MIT](LICENSE)
