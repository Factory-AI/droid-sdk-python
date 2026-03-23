#!/usr/bin/env python3
"""Mock droid exec subprocess for integration testing.

A standalone Python script that simulates ``droid exec`` by reading JSONL
from stdin and writing JSONL responses/notifications to stdout.

Behaviour is controlled via the ``MOCK_MODE`` environment variable:

- ``lifecycle``  — Handles initialize_session, add_user_message (sends a
  notification after the message response), and close lifecycle.
- ``permission`` — Sends a droid.request_permission server→client request
  after initialize_session, then processes the client's response.
- ``concurrent`` — Handles 3 methods; the second (list_skills) returns an
  error. Sends interleaved notifications between responses.
- ``nonjson``    — Writes debug text between valid JSON-RPC responses.
- ``echo``       — Echoes every request back as a success response with
  the params as the result. Useful for serialization fidelity tests.
- ``slow``       — Like echo but waits for a SIGUSR1 before responding.
  Useful for close-during-inflight tests. Falls back to a long sleep.
- ``hang``       — Reads from stdin but never responds (for timeout tests).

The script reads one JSONL line at a time from stdin, parses the JSON-RPC
envelope, and dispatches based on the method field.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sys
import time

MOCK_MODE = os.environ.get("MOCK_MODE", "lifecycle")

# Protocol constants
JSONRPC_VERSION = "2.0"
FACTORY_API_VERSION = "1.0.0"
FACTORY_PROTOCOL_VERSION = "1.1.0"


def write_jsonl(obj: dict) -> None:  # type: ignore[type-arg]
    """Write a JSON object as a single JSONL line to stdout."""
    line = json.dumps(obj, separators=(",", ":"))
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def make_response(request_id: str, result: dict) -> dict:  # type: ignore[type-arg]
    """Build a JSON-RPC success response."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "factoryApiVersion": FACTORY_API_VERSION,
        "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
        "type": "response",
        "id": request_id,
        "result": result,
    }


def make_error_response(
    request_id: str,
    code: int,
    message: str,
    data: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """Build a JSON-RPC error response."""
    error: dict = {"code": code, "message": message}  # type: ignore[type-arg]
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": JSONRPC_VERSION,
        "factoryApiVersion": FACTORY_API_VERSION,
        "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
        "type": "response",
        "id": request_id,
        "error": error,
    }


def make_notification(method: str, params: dict) -> dict:  # type: ignore[type-arg]
    """Build a JSON-RPC notification."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "factoryApiVersion": FACTORY_API_VERSION,
        "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
        "type": "notification",
        "method": method,
        "params": params,
    }


def make_server_request(request_id: str, method: str, params: dict) -> dict:  # type: ignore[type-arg]
    """Build a JSON-RPC server→client request."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "factoryApiVersion": FACTORY_API_VERSION,
        "factoryProtocolVersion": FACTORY_PROTOCOL_VERSION,
        "type": "request",
        "id": request_id,
        "method": method,
        "params": params,
    }


def session_notification(notif_type: str, data: dict | None = None) -> dict:  # type: ignore[type-arg]
    """Build a session_notification with the given type."""
    notif: dict = {"type": notif_type}  # type: ignore[type-arg]
    if data:
        notif.update(data)
    return make_notification(
        "droid.session_notification",
        {"notification": notif},
    )


def init_session_result(session_id: str = "test-session-1") -> dict:  # type: ignore[type-arg]
    """Standard initialize_session success result."""
    return {
        "sessionId": session_id,
        "session": {
            "id": session_id,
            "createdAt": "2025-01-01T00:00:00Z",
            "settings": {},
        },
        "settings": {
            "modelId": "test-model",
            "reasoningEffort": "medium",
        },
    }


def load_session_result(session_id: str = "test-session-1") -> dict:  # type: ignore[type-arg]
    """Standard load_session success result."""
    return {
        "session": {
            "id": session_id,
            "createdAt": "2025-01-01T00:00:00Z",
            "settings": {},
        },
        "settings": {
            "modelId": "test-model",
            "reasoningEffort": "medium",
        },
    }


# ── Mode handlers ─────────────────────────────────────────────


def handle_lifecycle() -> None:
    """Lifecycle mode: init → message (with notification) → close."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        request_id = msg.get("id", "")

        if method == "droid.initialize_session":
            session_id = msg.get("params", {}).get("sessionId", "test-session-1")
            write_jsonl(make_response(request_id, init_session_result(session_id)))
        elif method == "droid.add_user_message":
            # Send response first
            write_jsonl(make_response(request_id, {}))
            # Then send a notification
            write_jsonl(
                session_notification(
                    "assistant_text_delta",
                    {"delta": "Hello from the mock!"},
                )
            )
        elif method == "droid.load_session":
            session_id = msg.get("params", {}).get("sessionId", "test-session-1")
            write_jsonl(make_response(request_id, load_session_result(session_id)))
        else:
            # Default: empty success
            write_jsonl(make_response(request_id, {}))


def handle_permission() -> None:
    """Permission mode: after init, sends a permission request."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        request_id = msg.get("id", "")

        if method == "droid.initialize_session":
            session_id = msg.get("params", {}).get("sessionId", "test-session-1")
            write_jsonl(make_response(request_id, init_session_result(session_id)))
            # Send a permission request to the client
            write_jsonl(
                make_server_request(
                    "perm-req-1",
                    "droid.request_permission",
                    {
                        "toolUses": [
                            {
                                "name": "file_write",
                                "input": {"path": "/tmp/test.txt"},
                            }
                        ],
                        "options": ["approve", "deny", "cancel"],
                    },
                )
            )
        elif msg.get("type") == "response" and msg.get("id") == "perm-req-1":
            # Client responded to our permission request. Now
            # store the result to verify later (write as notification)
            result = msg.get("result", {})
            selected = result.get("selectedOption", "unknown")
            write_jsonl(
                session_notification(
                    "tool_result",
                    {"result": f"permission_response:{selected}"},
                )
            )
        else:
            write_jsonl(make_response(request_id, {}))


def handle_concurrent() -> None:
    """Concurrent mode: handles 3 methods; list_skills fails.

    Sends interleaved notifications between responses.
    """
    pending: list[tuple[str, str]] = []

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        request_id = msg.get("id", "")

        if method == "droid.initialize_session":
            session_id = msg.get("params", {}).get("sessionId", "test-session-1")
            write_jsonl(make_response(request_id, init_session_result(session_id)))
            continue

        # Queue the request
        pending.append((request_id, method))

        # Once we have 3 pending requests, respond to all with interleaved notifications
        if len(pending) >= 3:
            for _i, (req_id, meth) in enumerate(pending):
                # Interleave a notification before each response
                write_jsonl(
                    session_notification(
                        "droid_working_state_changed",
                        {"newState": "working"},
                    )
                )
                if meth == "droid.list_skills":
                    # This one fails
                    write_jsonl(
                        make_error_response(
                            req_id, -32603, "Internal error: skills unavailable"
                        )
                    )
                elif meth == "droid.list_mcp_servers":
                    write_jsonl(
                        make_response(
                            req_id,
                            {
                                "servers": [],
                                "summary": {
                                    "total": 0,
                                    "connected": 0,
                                    "connecting": 0,
                                    "failed": 0,
                                },
                            },
                        )
                    )
                elif meth == "droid.list_mcp_tools":
                    write_jsonl(make_response(req_id, {"tools": []}))
                else:
                    write_jsonl(make_response(req_id, {}))
            pending.clear()


def handle_nonjson() -> None:
    """Non-JSON mode: writes debug text between valid responses."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        request_id = msg.get("id", "")

        # Write some non-JSON debug text before the response
        # NOTE: Lines must NOT start with '{' or '[' — the transport
        # treats those as JSON and fires on_error for malformed ones.
        sys.stdout.write("DEBUG: processing request...\n")
        sys.stdout.flush()
        sys.stdout.write("info: method=" + method + "\n")
        sys.stdout.flush()

        if method == "droid.initialize_session":
            session_id = msg.get("params", {}).get("sessionId", "test-session-1")
            write_jsonl(make_response(request_id, init_session_result(session_id)))
        elif method == "droid.add_user_message":
            # More non-JSON between response and notification
            sys.stdout.write(">>> handling user message\n")
            sys.stdout.flush()
            write_jsonl(make_response(request_id, {}))
            sys.stdout.write("--- notification follows ---\n")
            sys.stdout.flush()
            write_jsonl(
                session_notification(
                    "assistant_text_delta",
                    {"delta": "Response with debug"},
                )
            )
        else:
            write_jsonl(make_response(request_id, {}))


def handle_echo() -> None:
    """Echo mode: echoes requests back as success responses."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        request_id = msg.get("id", "")
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "droid.initialize_session":
            session_id = params.get("sessionId", "test-session-1")
            write_jsonl(make_response(request_id, init_session_result(session_id)))
        else:
            # Echo the params back as the result for fidelity testing
            write_jsonl(make_response(request_id, params))


def handle_slow() -> None:
    """Slow mode: reads requests but delays response.

    Useful for testing close-during-inflight.
    Responds to initialize_session immediately, but delays all other responses.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        request_id = msg.get("id", "")

        if method == "droid.initialize_session":
            session_id = msg.get("params", {}).get("sessionId", "test-session-1")
            write_jsonl(make_response(request_id, init_session_result(session_id)))
        else:
            # Sleep for a long time (will be killed by test)
            time.sleep(300)
            write_jsonl(make_response(request_id, {}))


def handle_hang() -> None:
    """Hang mode: reads from stdin but never responds."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        # Parse but do nothing — hang forever
        with contextlib.suppress(json.JSONDecodeError):
            json.loads(line)
        # Never write a response


MODE_HANDLERS = {
    "lifecycle": handle_lifecycle,
    "permission": handle_permission,
    "concurrent": handle_concurrent,
    "nonjson": handle_nonjson,
    "echo": handle_echo,
    "slow": handle_slow,
    "hang": handle_hang,
}


def main() -> None:
    """Entry point for the mock subprocess."""
    # Ignore SIGTERM gracefully to allow testing SIGKILL escalation
    # when mode requires it; otherwise let it terminate normally
    if MOCK_MODE == "hang":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    handler = MODE_HANDLERS.get(MOCK_MODE)
    if handler is None:
        sys.stderr.write(f"Unknown MOCK_MODE: {MOCK_MODE}\n")
        sys.exit(1)

    with contextlib.suppress(BrokenPipeError, KeyboardInterrupt):
        handler()


if __name__ == "__main__":
    main()
