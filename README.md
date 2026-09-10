# Support AI Lab

### Stop Guessing, Start Measuring

[![Tests](https://github.com/rocky-bhatia86/customer-support-observability-lab/actions/workflows/tests.yml/badge.svg?branch=failure-scenarios)](https://github.com/rocky-bhatia86/customer-support-observability-lab/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

A hands-on lab for AI observability: a real multi-agent customer support
system, with real production failure modes, real tracing, and a real
LLM-as-a-judge evaluator layered on top — staged across branches so each
capability can be studied in isolation.

Ask it something in the chat UI and watch a live orchestrator dynamically
route your ticket through whichever of 7 specialist agents it actually
needs, iterate against a quality gate, and either resolve or escalate —
exactly like a production agentic system would.

## Quickstart

```bash
git checkout failure-scenarios      # start here, not main -- see "Branches" below
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
| `main` | Baseline: a clean 4-agent pipeline, no injected failures |
| `failure-scenarios` | The full dynamic multi-agent system, a real chat UI, and 4 controlled production failures |
| `langfuse-observability` | Real tracing (Langfuse), layered on the same code |
| `llm-judge-eval` | LLM-as-a-judge evaluation, scored against real traces |

Start at `failure-scenarios` — `main` predates the chat UI and the dynamic
agent system entirely.

## Architecture

```
Ticket -> Orchestrator (classify + pick agent plan)
              |
              v
   dynamically runs whichever of:
     Knowledge Agent, Account/Billing Agent,
     Impact/Diagnostics Agent, Account Access Agent
   the plan calls for
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
instrument with Langfuse tracing.

## Testing

```bash
pytest -q
```

Tests never call a real LLM — `call_llm` is monkeypatched, so `pytest` runs
without network access or an API key. This is also why CI needs no secrets.

## License

[MIT](LICENSE)
