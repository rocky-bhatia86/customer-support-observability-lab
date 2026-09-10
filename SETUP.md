# Support AI Lab — Setup Guide

This guide assumes nothing about the machine you're using. Follow it in
order the first time; each step states exactly what to check before moving
to the next.

The lab is staged across git branches. Each branch adds exactly one
capability on top of the previous one:

| Branch | Adds |
|---|---|
| `main` | The full multi-agent system, MCP tool-calling, a real chat UI, and 4 controlled production failures |
| `langfuse-observability` | Real tracing (Langfuse), layered on the same code |
| `llm-judge-eval` | LLM-as-a-judge evaluation, scored against real traces |

**Start at `main`.** Do not skip ahead — later stages assume the previous
stage is already working.

---

## 0. Getting the Code Onto This Machine

```bash
git clone https://github.com/rocky-bhatia86/customer-support-observability-lab.git
```

Confirm all branches are present:

```bash
cd customer-support-observability-lab
git branch -a
# expect: main, langfuse-observability, llm-judge-eval
```

---

## 1. Prerequisites

| Requirement | Needed for | Check with |
|---|---|---|
| Python 3.11+ | All stages | `python3 --version` |
| Git | All stages | `git --version` |
| An OpenAI (or OpenAI-compatible) API key | All stages | — provided by you |
| Docker Desktop | Only if self-hosting Langfuse (Stage 2/3) | `docker --version` |

Docker is **not required** for Stage 1. If Docker is unavailable, Stage 2/3
can use a free Langfuse Cloud account instead — see Section 3.

---

## 2. Stage 1 — `main`

```bash
cd customer-support-observability-lab
git checkout main

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e .

cp .env.example .env
```

Open `.env` and set:

```
OPENAI_API_KEY=<your key>
```

Every other value already has a working default. Leave `OPENAI_BASE_URL`
blank unless pointing at a specific OpenAI-compatible gateway (e.g. an
internal model-serving endpoint).

Start the server:

```bash
python scripts/run_server.py
```

Open **http://localhost:8000**. The chat UI shows 5 suggested tickets and a
**Checker: v1 / v2** toggle in the header.

### Verification

1. Click any suggested ticket. It resolves within roughly 10–20 seconds —
   these are real LLM calls, so some wait time is expected.
2. Open **Show Agent Activity** and confirm real agent names and real data
   are shown — each specialist agent's data lookup is a real MCP tool call
   to `support_ai.mcp_server` (a subprocess spawned on first use, then
   reused for the life of the server).
3. Switch the header toggle to **v2** and re-run the same ticket. Some
   tickets (e.g. "I need a refund") will now loop and escalate — identical
   code, one setting changed. This is the intended behavior (Failure D), not
   a defect.

**If a request fails with a connection error despite a valid API key:**
`src/support_ai/config.py` includes a fix for a known `openai` SDK issue
(an unset `base_url` resolving incorrectly). Confirm the code includes this
fix; if not, re-copy the repository.

Stage 1 is fully functional at this point — no Langfuse or Docker required.

---

## 3. Stage 2 — `langfuse-observability`

```bash
git checkout langfuse-observability
pip install -e .
```

The `.env` file from Stage 1 carries forward automatically — it is untracked
by git, so switching branches does not affect it. Only the Langfuse keys
need to be added.

**Choose one path:**

### Option A — Langfuse Cloud (no Docker required)

1. Create a free account at the Langfuse Cloud console.
2. Create a project and generate an API key pair.
3. Add to `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```

### Option B — Self-Hosted Langfuse (requires Docker, fully offline)

1. Confirm Docker Desktop is running: `docker info` should return without
   error.
2. In a separate folder (outside this repository):
   ```bash
   git clone https://github.com/langfuse/langfuse.git langfuse-local
   cd langfuse-local
   docker compose up -d
   ```
3. After 1–2 minutes, open **http://localhost:3000**, create a local
   account and project, and generate an API key pair.
4. Add to this repository's `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=http://localhost:3000
   ```

   **Port conflicts:** if `docker compose up -d` reports a port already in
   use, another process on the machine is occupying one of Langfuse's ports
   (commonly 5432, 6379, 8123, 9000, 9090, or 9091). Edit `docker-compose.yml`
   in the `langfuse-local` folder and remap the host side of the conflicting
   `ports:` entry (e.g. `5432:5432` → `15432:5432`); the container side must
   stay unchanged.

### Verification

```bash
python scripts/run_server.py
```
Run a ticket, then open the Langfuse project (Cloud or local) and navigate to
**Tracing → Traces**. A `support_ticket_workflow` trace should appear with a
nested span tree (classify → retrieve/lookup → draft → check).

---

## 4. Stage 3 — `llm-judge-eval`

```bash
git checkout llm-judge-eval
pip install -e .
```

One-time setup (safe to re-run):

```bash
python scripts/seed_prompts.py
python scripts/seed_dataset.py
```

Run an evaluation:

```bash
python scripts/run_experiment.py --checker-version v1
python scripts/run_experiment.py --checker-version v2
```

Each run prints a `dataset_run_url` with per-ticket scores. In the Langfuse
UI, **Datasets → support-tickets-eval → Runs** shows both runs side by side
for direct comparison.

---

## 5. Sanity Check (any stage)

```bash
python -m pytest -q
```

All tests should pass (7, on `main` and later branches). A
failure immediately after moving to a new machine is almost always a missed
`pip install -e .` after a branch switch, or a `.venv` that did not transfer
correctly — delete `.venv` and recreate it using the commands in Section 2.

---

## Explicit Non-Assumptions

- Docker is not assumed or required for Stage 1.
- `.env.example` defaults are assumed correct as shipped; only
  `OPENAI_API_KEY` (and later, the Langfuse keys) require values.
- Longer response times are expected behavior, not a fault — real,
  multi-iteration LLM calls under `v2` can take 30–90 seconds. The chat UI's
  live step-by-step activity indicates progress; a static screen for a few
  seconds between steps is normal.
