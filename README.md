# Stop Guessing, Start Measuring
## Customer Support Ticket Triage & Resolution Assistant

A hands-on lab for AI observability, production failure analysis, evaluations,
and LLM-as-a-judge. This repo currently contains only **Stages 0-12**: a clean
multi-agent baseline and a separate branch with controlled, realistic
production failures. No tracing, evaluation framework, LLM-judge, or
dashboard has been added yet -- see `LAB_PLAN.md` for what's next.

## Setup

```bash
cd customer-support-observability-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

## Run

```bash
python scripts/run_ticket.py TCK-001
python scripts/run_batch.py
python scripts/run_batch.py --output-json /tmp/results.json
```

## Test

```bash
pytest -q
```

Tests never call the real OpenAI API -- `call_llm` is monkeypatched, so
`pytest` works without network access or an API key.

## Branches

- `main` — baseline, tag `baseline-v1`: clean workflow, no injected failures.
- `failure-scenarios` — tag `failures-v1`: same workflow with four controlled
  production failures layered on top (see `LAB_PLAN.md`).

## Architecture

```
Ticket -> Orchestrator (classify) -> KB Retrieval -> Drafter -> Quality Checker
                                          ^                          |
                                          +----- REJECT_AND_RETRIEVE -+
                                                 (max 5 iterations)
```

Every LLM call goes through the single `support_ai.llm_client.call_llm`
function -- this is the seam the next lab stage instruments with Langfuse.
