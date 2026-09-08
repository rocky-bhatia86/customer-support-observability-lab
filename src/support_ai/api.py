"""Local HTTP API + static UI host for the Support AI Lab chat interface.

This is the only workshop-only addition on this branch that isn't pure
agent logic: it runs the real WorkflowRunner against real tickets and
serves the web/ UI so the chat talks to the actual multi-agent backend,
not scripted data. No observability endpoints exist here -- that's added
on top in the langfuse-observability stage.
"""
from __future__ import annotations

import dataclasses
import json
import queue
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from support_ai.config import load_config
from support_ai.models import Ticket, WorkflowStep
from support_ai.orchestrator import WorkflowRunner

_ROOT = Path(__file__).resolve().parents[2]
_WEB_DIR = _ROOT / "web"
_TICKETS_PATH = _ROOT / "data" / "tickets.json"
_ACCOUNTS_PATH = _ROOT / "data" / "accounts.json"
_ACCESS_PATH = _ROOT / "data" / "access_records.json"


def _list_demo_accounts() -> list[dict]:
    """Union of every account_id referenced in the demo data, so the UI can
    let a free-typed chat message "act as" one of them -- otherwise only
    the 6 pre-scripted tickets ever have real account/access data to look
    up, and any other question always looks anonymous."""
    accounts = {a["account_id"]: {"account_id": a["account_id"], "plan": a["plan"]}
                for a in json.loads(_ACCOUNTS_PATH.read_text())}
    for r in json.loads(_ACCESS_PATH.read_text()):
        accounts.setdefault(r["account_id"], {"account_id": r["account_id"], "plan": None})
        if r["locked"]:
            accounts[r["account_id"]]["note"] = "locked"
    return sorted(accounts.values(), key=lambda a: a["account_id"])


def _serialize_step(s: WorkflowStep) -> dict:
    return {
        "iteration": s.iteration,
        "agent": s.agent,
        "action": s.action,
        "detail": s.detail,
        "elapsed_seconds": s.elapsed_seconds,
        "prompt_tokens": s.prompt_tokens,
        "completion_tokens": s.completion_tokens,
        "meta": s.meta,
    }


def _serialize_result(result, checker_prompt_version: str):
    return {
        "ticket_id": result.ticket_id,
        "category": result.category,
        "status": result.status,
        "final_response": result.final_response,
        "iterations": result.iterations,
        "elapsed_seconds": result.elapsed_seconds,
        "total_prompt_tokens": result.total_prompt_tokens,
        "total_completion_tokens": result.total_completion_tokens,
        "checker_prompt_version": checker_prompt_version,
        "steps": [_serialize_step(s) for s in result.steps],
    }


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    base_config = load_config()
    tickets = json.loads(_TICKETS_PATH.read_text())
    tickets_by_id = {t["id"]: t for t in tickets}

    # Lets the workshop flip CHECKER_PROMPT_VERSION live (Failure D: "last
    # week's model/prompt bump") without restarting the server -- run the
    # happy path under v1, then flip to v2 to reveal the same request
    # failing on the identical codebase.
    live_state = {"checker_prompt_version": base_config.checker_prompt_version}
    runners_by_version: dict[str, WorkflowRunner] = {}

    def current_runner() -> WorkflowRunner:
        version = live_state["checker_prompt_version"]
        if version not in runners_by_version:
            runners_by_version[version] = WorkflowRunner(
                dataclasses.replace(base_config, checker_prompt_version=version)
            )
        return runners_by_version[version]

    @app.get("/")
    def index():
        return send_from_directory(_WEB_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(_WEB_DIR, filename)

    @app.get("/api/tickets")
    def list_tickets():
        return jsonify(tickets)

    @app.get("/api/accounts")
    def list_accounts():
        return jsonify(_list_demo_accounts())

    @app.get("/api/config")
    def get_config():
        return jsonify({"checker_prompt_version": live_state["checker_prompt_version"]})

    @app.post("/api/config")
    def set_config():
        body = request.get_json(force=True, silent=True) or {}
        version = body.get("checker_prompt_version")
        if version not in ("v1", "v2"):
            return jsonify({"error": "checker_prompt_version must be 'v1' or 'v2'"}), 400
        live_state["checker_prompt_version"] = version
        return jsonify({"checker_prompt_version": live_state["checker_prompt_version"]})

    @app.post("/api/run")
    def run_ticket():
        body = request.get_json(force=True, silent=True) or {}
        ticket_id = (body.get("ticket_id") or "").strip()
        text = (body.get("text") or "").strip()

        if ticket_id:
            match = tickets_by_id.get(ticket_id)
            if not match:
                return jsonify({"error": f"Unknown ticket_id {ticket_id}"}), 404
            ticket = Ticket(id=match["id"], text=match["text"], account_id=match.get("account_id"))
        elif text:
            account_id = (body.get("account_id") or "").strip() or None
            ticket = Ticket(id=f"ADHOC-{uuid.uuid4().hex[:8]}", text=text, account_id=account_id)
        else:
            return jsonify({"error": "Provide ticket_id or text"}), 400

        try:
            result = current_runner().run(ticket)
        except Exception as exc:  # noqa: BLE001 - surface to the demo UI as a clear error
            return jsonify({"error": str(exc)}), 502

        return jsonify(_serialize_result(result, live_state["checker_prompt_version"]))

    @app.post("/api/run/stream")
    def run_ticket_stream():
        body = request.get_json(force=True, silent=True) or {}
        ticket_id = (body.get("ticket_id") or "").strip()
        text = (body.get("text") or "").strip()

        if ticket_id:
            match = tickets_by_id.get(ticket_id)
            if not match:
                return jsonify({"error": f"Unknown ticket_id {ticket_id}"}), 404
            ticket = Ticket(id=match["id"], text=match["text"], account_id=match.get("account_id"))
        elif text:
            account_id = (body.get("account_id") or "").strip() or None
            ticket = Ticket(id=f"ADHOC-{uuid.uuid4().hex[:8]}", text=text, account_id=account_id)
        else:
            return jsonify({"error": "Provide ticket_id or text"}), 400

        events: queue.Queue = queue.Queue()
        runner = current_runner()
        version_used = live_state["checker_prompt_version"]

        def worker():
            try:
                result = runner.run(ticket, on_step=lambda s: events.put(("step", s)))
                events.put(("done", result))
            except Exception as exc:  # noqa: BLE001 - surface to the demo UI as a clear error
                events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

        def generate():
            while True:
                kind, payload = events.get()
                if kind == "step":
                    yield _sse("step", _serialize_step(payload))
                elif kind == "done":
                    yield _sse("done", _serialize_result(payload, version_used))
                    break
                else:
                    yield _sse("error", {"error": payload})
                    break

        return Response(generate(), mimetype="text/event-stream")

    return app
