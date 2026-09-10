"""Sync bridge to the MCP tool server (support_ai.mcp_server).

The MCP SDK is async-native; this app (Flask, WorkflowRunner, every agent)
is fully synchronous. Rather than convert the whole app to async for this,
one background thread runs a dedicated asyncio event loop with a single
long-lived "driver" coroutine that holds the MCP client session open for
the process's entire lifetime (spawned once, reused for every call).

anyio's cancel scopes require a context manager to be entered and exited
in the same task -- so the driver keeps the `async with` block open itself
and is fed requests through a queue, rather than the client trying to
enter/exit the session piecemeal across separately-submitted tasks (which
breaks that invariant with a "cancel scope in a different task" error).

call_tool() is the only function other modules need.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sys
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_loop: asyncio.AbstractEventLoop | None = None
_request_queue: asyncio.Queue | None = None
_start_lock = threading.Lock()
_ready = threading.Event()


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "support_ai.mcp_server"],
        cwd=str(Path(__file__).resolve().parents[1]),
    )


async def _driver(queue: asyncio.Queue) -> None:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            _ready.set()
            while True:
                name, arguments, response_future = await queue.get()
                try:
                    result = await session.call_tool(name, arguments)
                    response_future.set_result(result)
                except Exception as exc:  # noqa: BLE001 - surface to the caller, don't kill the driver
                    response_future.set_exception(exc)


def _run_loop(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_driver(queue))


def _ensure_started() -> None:
    global _loop, _request_queue
    if _loop is not None:
        return
    with _start_lock:
        if _loop is not None:
            return
        loop = asyncio.new_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        thread = threading.Thread(target=_run_loop, args=(loop, queue), daemon=True, name="mcp-client-loop")
        thread.start()
        if not _ready.wait(timeout=15):
            raise RuntimeError("MCP server did not become ready in time")
        _loop, _request_queue = loop, queue


def call_tool(name: str, arguments: dict) -> dict:
    """Calls an MCP tool by name and returns its JSON result as a dict.
    Starts the MCP server subprocess + client session on first use;
    subsequent calls reuse the same live connection."""
    _ensure_started()
    assert _loop is not None and _request_queue is not None

    response_future: concurrent.futures.Future = concurrent.futures.Future()
    asyncio.run_coroutine_threadsafe(
        _request_queue.put((name, arguments, response_future)), _loop
    ).result(timeout=5)

    result = response_future.result(timeout=30)
    return json.loads(result.content[0].text)
