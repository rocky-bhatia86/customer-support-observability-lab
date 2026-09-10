# Support AI Lab — Setup Guide

This assumes nothing about the machine you're on. Follow it top to bottom the
first time; each numbered step says exactly what to check before moving on.

The lab is staged across git branches — each one adds exactly one capability
on top of the last:

| Branch | Adds |
|---|---|
| `failure-scenarios` | The full multi-agent system, real chat UI, 4 controlled production failures |
| `langfuse-observability` | Real tracing (Langfuse) on top of the same code |
| `llm-judge-eval` | LLM-as-a-judge evaluation, scored against real traces |

Start at `failure-scenarios`. Don't jump ahead — the later stages assume the
earlier one is already working.

---

## 0. Getting the code onto this machine

There is currently **no git remote** for this repo (no GitHub/GitLab URL to
`git clone`). Pick one:

- **Simplest**: copy the whole project folder (it includes `.git/`, so all
  branches and history come with it) via USB drive, AirDrop, `rsync`, a
  shared drive, whatever you have. No git server needed.
- **Proper clone workflow**: push this repo to a GitHub/GitLab repo you
  control first, then `git clone <that-url>` on the new machine. Ask me to
  set this up if you want it — it's a few commands, not done yet.

Either way, once the folder exists on the new machine, confirm all 4
branches came with it:

```bash
cd customer-support-observability-lab
git branch -a
# expect: main, failure-scenarios, langfuse-observability, llm-judge-eval
```

---

## 1. Prerequisites (check these before anything else)

| Requirement | Needed for | Check with |
|---|---|---|
| Python 3.11+ | Everything | `python3 --version` |
| `git` | Everything | `git --version` |
| An OpenAI (or OpenAI-compatible) API key | Everything | — you provide this |
| Docker Desktop | **Only** if self-hosting Langfuse for Stage 2/3 | `docker --version` |

If you don't have Docker and don't want to install it: you can skip
self-hosting and use a free Langfuse Cloud account instead for Stage 2/3 —
covered in that section. **Docker is not required for Stage 1
(`failure-scenarios`) at all.**

---

## 2. Stage 1 — `failure-scenarios` (do this first, every time, on a new machine)

```bash
cd customer-support-observability-lab
git checkout failure-scenarios

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e .

cp .env.example .env
```

Now open `.env` and fill in:

```
OPENAI_API_KEY=<your real key>
```

Everything else in `.env` already has working defaults — **do not change
`OPENAI_BASE_URL`** unless you specifically want to point at a different
provider (e.g. a company-internal gateway). Leave it blank to use OpenAI's
own API directly.

Run it:

```bash
python scripts/run_server.py
```

Open **http://localhost:8000**. You should see the chat UI with 5 suggested
tickets and a "Checker: v1 / v2" toggle in the header.

### Verify it's actually working

1. Click any suggested ticket. It should resolve normally within ~10-20
   seconds (real LLM calls take time — this is not a bug, don't assume it's
   stuck).
2. Click "Show Agent Activity" and confirm you see real agent names and real
   data (not placeholder text).
3. Flip the header toggle to **v2**, re-run the same ticket. Some tickets
   (e.g. "I need a refund") will now loop and escalate — same code, one
   setting changed. That's Failure D, working as intended, not a bug.

If step 1 fails with a connection error even though your API key is valid:
check `src/support_ai/config.py` — this repo already has a fix for a known
`openai` SDK bug (an unset `base_url` resolving incorrectly). If you're
somehow on a version of this code from before that fix, `git pull`/re-copy
the folder.

**Stage 1 is fully working with just this — no Langfuse, no Docker, nothing
else needed.**

---

## 3. Stage 2 — `langfuse-observability` (adds real tracing)

```bash
git checkout langfuse-observability
pip install -e .          # picks up the added langfuse dependency
```

Your `.env` from Stage 1 carries forward automatically (it's untracked by
git, so switching branches doesn't touch it) — you only need to *add* the
Langfuse keys, not redo everything.

**Choose one, based on whether you have Docker:**

### Option A — No Docker: Langfuse Cloud (fastest)
1. Sign up free at the Langfuse Cloud console.
2. Create a project, generate an API key pair.
3. Add to `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```

### Option B — Have Docker: self-host locally (fully offline)
1. Confirm Docker Desktop is actually running (`docker info` should not
   error — a common miss is having Docker *installed* but not *started*).
2. In a **separate** folder (not inside this repo):
   ```bash
   git clone https://github.com/langfuse/langfuse.git langfuse-local
   cd langfuse-local
   docker compose up -d
   ```
3. Wait ~1-2 minutes, then open **http://localhost:3000**, sign up (local
   account, nothing leaves your machine), create a project, generate keys.
4. Add to this repo's `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=http://localhost:3000
   ```

   **If `docker compose up -d` fails with a port-already-in-use error**:
   something else on your machine is using one of Langfuse's ports
   (5432, 6379, 8123, 9000, 9090, 9091 are the common culprits). Edit
   `docker-compose.yml` in that `langfuse-local` folder and remap the
   *left* side of the conflicting `ports:` line to an unused port (e.g.
   `5432:5432` → `15432:5432`) — the right side must stay unchanged.

### Verify Stage 2

```bash
python scripts/run_server.py
```
Run a ticket, then open your Langfuse project (Cloud or local) →
**Tracing → Traces**. You should see a `support_ticket_workflow` trace with
a nested tree (classify → retrieve/lookup steps → draft → check).

---

## 4. Stage 3 — `llm-judge-eval` (adds LLM-as-a-judge)

```bash
git checkout llm-judge-eval
pip install -e .
```

One-time seeding (safe to re-run anytime):

```bash
python scripts/seed_prompts.py
python scripts/seed_dataset.py
```

Run the evaluation:

```bash
python scripts/run_experiment.py --checker-version v1
python scripts/run_experiment.py --checker-version v2
```

Each run prints a `dataset_run_url` — open it to see per-ticket scores.
In the Langfuse UI: **Datasets → support-tickets-eval → Runs** to compare
the two runs side by side.

---

## 5. Sanity check at any stage

```bash
python -m pytest -q
```
Should show all tests passing (7 on `failure-scenarios` and later branches).
If this fails right after copying the folder to a new machine, it's almost
always a missed `pip install -e .` after switching branches, or a stale
`.venv` from the old machine that didn't come with you correctly — delete
`.venv` and recreate it fresh with the commands in Section 2.

---

## Things this guide deliberately does NOT assume

- That you have Docker, or want to install it — Stage 1 needs neither.
- That `.env.example`'s defaults are fine to change — only `OPENAI_API_KEY`
  (and later, the Langfuse keys) need to be filled in; everything else is
  already correct.
- That "it's taking a while" means something is broken — real LLM calls,
  especially multi-iteration ones under `v2`, can take 30-90 seconds. Watch
  the chat UI's live step-by-step activity, not just a spinner.
