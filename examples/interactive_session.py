#!/usr/bin/env python3
"""Interactive session example for the Factory Droid Python SDK.

Demonstrates the SDK's full capabilities by rendering ALL intermediate activity
from a Droid session with ANSI-colored output:

  - Assistant text deltas (streamed char-by-char)
  - Thinking text deltas (gray, with [Thinking] prefix)
  - Tool calls (yellow: tool name + input summary)
  - Tool results (green for success, red for errors)
  - Tool progress updates
  - Token usage updates
  - Error events (red)
  - Permission requests (auto-approve or prompt user)
  - Turn completion with final token stats
  - MCP status changes
  - Session title updates

Usage:
    python examples/interactive_session.py [--cwd /path/to/project]

Requires the ``droid`` CLI to be installed and available on PATH
(or at ``~/.local/bin/droid``).

Simpler alternative using query():

    import asyncio
    from droid_sdk import query, AssistantTextDelta, TurnComplete

    async def main() -> None:
        async for msg in query("Hello!", cwd="."):
            if isinstance(msg, AssistantTextDelta):
                print(msg.text, end="", flush=True)
            elif isinstance(msg, TurnComplete):
                print()

    asyncio.run(main())
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from droid_sdk import (
    AssistantTextDelta,
    ConnectionError,
    DroidClient,
    DroidClientError,
    ErrorEvent,
    ProcessExitError,
    ProcessTransport,
    StreamMessage,
    ThinkingTextDelta,
    TimeoutError,
    TokenUsageUpdate,
    ToolConfirmationOutcome,
    ToolProgress,
    ToolResult,
    ToolUse,
    TurnComplete,
    WorkingStateChanged,
)

# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------

# Standard ANSI escape codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_GRAY = "\033[90m"


def _colored(text: str, *codes: str) -> str:
    """Wrap text in ANSI escape codes."""
    prefix = "".join(codes)
    return f"{prefix}{text}{_RESET}"


# ---------------------------------------------------------------------------
# Tracking state for deduplication and clean output
# ---------------------------------------------------------------------------

# Track whether we're in the middle of streaming text (to manage newlines)
_streaming_text = False

# Track the last MCP summary string to deduplicate notifications
_last_mcp_summary: str | None = None

# Track the last token usage to only print at turn end
_last_token_usage: TokenUsageUpdate | None = None


def _ensure_newline() -> None:
    """Print a newline if we were streaming text inline."""
    global _streaming_text
    if _streaming_text:
        print()
        _streaming_text = False


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------


def render_message(msg: StreamMessage) -> None:
    """Render a single StreamMessage with ANSI colors."""
    global _streaming_text, _last_token_usage

    if isinstance(msg, AssistantTextDelta):
        # Stream assistant text char-by-char (inline, no newline)
        print(msg.text, end="", flush=True)
        _streaming_text = True

    elif isinstance(msg, ThinkingTextDelta):
        # Thinking text in gray with prefix (inline, no newline)
        if not _streaming_text:
            print(_colored("[thinking] ", _GRAY, _DIM), end="", flush=True)
            _streaming_text = True
        print(_colored(msg.text, _GRAY, _DIM), end="", flush=True)

    elif isinstance(msg, ToolUse):
        _ensure_newline()
        print()  # blank line before tool call
        input_summary = json.dumps(msg.tool_input, ensure_ascii=False)
        if len(input_summary) > 120:
            input_summary = input_summary[:117] + "..."
        print(_colored("[tool] ", _YELLOW, _BOLD) + _colored(msg.tool_name, _YELLOW))
        print(_colored(f"  {input_summary}", _DIM))

    elif isinstance(msg, ToolResult):
        _ensure_newline()
        content_preview = _content_preview(msg.content)
        if msg.is_error:
            tag = "[error] "
            name = msg.tool_name or "unknown"
            print(_colored(tag, _RED, _BOLD) + _colored(f"{name} (error)", _RED))
            print(_colored(f"  {content_preview}", _RED))
        else:
            tag = "[result] "
            name = msg.tool_name or "unknown"
            print(_colored(tag, _GREEN, _BOLD) + _colored(f"{name} (success)", _GREEN))
            print(_colored(f"  {content_preview}", _DIM))
        print()  # blank line after tool result

    elif isinstance(msg, ToolProgress):
        _ensure_newline()
        print(_colored("[progress] ", _CYAN, _BOLD) + _colored(msg.tool_name, _CYAN))
        print(_colored(f"  {msg.content}", _CYAN))

    elif isinstance(msg, WorkingStateChanged):
        # Suppress state changes entirely — tool calls and results already
        # indicate what's happening, and "Streaming Assistant Message" is
        # obvious from the text appearing on screen.
        pass

    elif isinstance(msg, TokenUsageUpdate):
        # Stash the latest token usage; we only print it at turn end.
        _last_token_usage = msg

    elif isinstance(msg, ErrorEvent):
        _ensure_newline()
        print()
        print(_colored(f"[error] {msg.error_type}: {msg.message}", _RED, _BOLD))
        print()

    elif isinstance(msg, TurnComplete):
        _ensure_newline()
        print()
        # Print token usage (from stashed update or TurnComplete payload)
        tu = msg.token_usage
        if tu is not None:
            total = tu.input_tokens + tu.output_tokens
            print(
                _colored(
                    f"[tokens] {total:,} total "
                    f"(in={tu.input_tokens:,}, out={tu.output_tokens:,}, "
                    f"cache_read={tu.cache_read_tokens:,}, "
                    f"cache_write={tu.cache_write_tokens:,})",
                    _DIM,
                )
            )
        elif _last_token_usage is not None:
            t = _last_token_usage
            total = t.input_tokens + t.output_tokens
            print(
                _colored(
                    f"[tokens] {total:,} total "
                    f"(in={t.input_tokens:,}, out={t.output_tokens:,}, "
                    f"cache_read={t.cache_read_tokens:,}, "
                    f"cache_write={t.cache_write_tokens:,})",
                    _DIM,
                )
            )
        print(_colored("[done] Turn complete", _GREEN, _BOLD))
        print()  # blank line before next prompt
        # Reset stashed token usage for next turn
        _last_token_usage = None

    else:
        # Future-proof: render unknown message types
        _ensure_newline()
        print(_colored(f"  [?] {type(msg).__name__}: {msg}", _DIM))


def _content_preview(content: str | list[object], max_len: int = 100) -> str:
    """Create a truncated preview of tool result content."""
    if isinstance(content, list):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    # Collapse whitespace for display
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# Notification listener for events not in receive_response()
# ---------------------------------------------------------------------------


def on_raw_notification(notification: dict[str, object]) -> None:
    """Handle notifications not covered by receive_response().

    Renders MCP status changes, session title updates, and other
    notification types that are not mapped to StreamMessage.
    """
    global _last_mcp_summary

    params = notification.get("params")
    if not isinstance(params, dict):
        return
    inner = params.get("notification")
    if not isinstance(inner, dict):
        return

    notif_type = inner.get("type")

    if notif_type == "mcp_status_changed":
        servers = inner.get("servers", [])
        summary = inner.get("summary", {})
        connected = summary.get("connected", 0)
        total = summary.get("total", 0)

        # Build a summary string to detect duplicates
        server_lines: list[str] = []
        if isinstance(servers, list):
            for srv in servers:
                if isinstance(srv, dict):
                    name = srv.get("name", "?")
                    status = srv.get("status", "?")
                    server_lines.append(f"  {name}: {status}")
        current_summary = f"{connected}/{total}|" + "|".join(server_lines)

        # Only print if the summary actually changed
        if current_summary == _last_mcp_summary:
            return
        _last_mcp_summary = current_summary

        print()
        print(
            _colored(
                f"[mcp] servers ({connected}/{total} connected):",
                _MAGENTA,
            )
        )
        for line in server_lines:
            print(_colored(line, _DIM))

    elif notif_type == "session_title_updated":
        title = inner.get("title", "")
        print(_colored(f"[title] {title}", _BLUE, _BOLD))

    elif notif_type == "mcp_auth_required":
        server_name = inner.get("serverName", "?")
        auth_url = inner.get("authUrl", "?")
        print(_colored(f"[mcp] auth required for {server_name}", _YELLOW, _BOLD))
        print(_colored(f"  URL: {auth_url}", _DIM))

    elif notif_type == "mcp_auth_completed":
        server_name = inner.get("serverName", "?")
        outcome = inner.get("outcome", "?")
        print(_colored(f"[mcp] auth {outcome} for {server_name}", _YELLOW))

    elif notif_type == "mission_state_changed":
        state = inner.get("state", "?")
        print(_colored(f"[state] mission: {state}", _MAGENTA, _BOLD))

    elif notif_type == "permission_resolved":
        option = inner.get("selectedOption", "?")
        print(_colored(f"[state] permission resolved: {option}", _DIM))


# ---------------------------------------------------------------------------
# Main session loop
# ---------------------------------------------------------------------------


async def main(cwd: str, exec_path: str) -> None:
    """Run an interactive Droid session with full activity rendering."""
    transport = ProcessTransport(exec_path=exec_path, cwd=cwd)

    async with DroidClient(transport=transport) as client:
        # Register raw notification listener for events outside receive_response()
        client.on_notification(on_raw_notification)

        # Register permission handler (auto-approve all)
        def handle_permission(params: dict[str, object]) -> str:
            """Auto-approve all permission requests."""
            tool_uses = params.get("toolUses")
            if isinstance(tool_uses, list):
                for tool in tool_uses:
                    if isinstance(tool, dict):
                        tool_use = tool.get("toolUse")
                        if isinstance(tool_use, dict):
                            name = tool_use.get("name", "unknown")
                            print(
                                _colored(
                                    f"[state] auto-approving: {name}",
                                    _YELLOW,
                                    _BOLD,
                                )
                            )
            return ToolConfirmationOutcome.ProceedOnce.value

        # Initialize session
        print(f"Executable: {exec_path}")
        print(f"Working directory: {cwd}")
        print()

        try:
            result = await client.initialize_session(
                machine_id="interactive-example",
                cwd=cwd,
            )
            print(f"Session ID: {result.session_id}")
            print(f"Model: {result.settings.model_id}")
            if result.available_models:
                print(f"Available models: {len(result.available_models)}")
        except TimeoutError:
            print(_colored("ERROR: Session initialization timed out.", _RED, _BOLD))
            return
        except ConnectionError as e:
            print(_colored(f"ERROR: Could not connect: {e}", _RED, _BOLD))
            return

        # Brief pause to let MCP notifications arrive before first prompt
        await asyncio.sleep(1.0)

        # Interactive loop
        print()
        print("Type your messages below. Press Ctrl+C or type 'exit' to quit.")

        while True:
            try:
                # Small delay for pending notification flush
                await asyncio.sleep(0.1)
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(_colored("\n> ", _CYAN, _BOLD))
                )
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", ":q"):
                print("Goodbye!")
                break

            try:
                await client.add_user_message(text=user_input)

                # Stream the response using receive_response()
                async for msg in client.receive_response():
                    render_message(msg)

            except ProcessExitError as e:
                print(_colored(f"\n[error] Droid process exited: {e}", _RED, _BOLD))
                break
            except DroidClientError as e:
                print(_colored(f"\n[error] {e}", _RED, _BOLD))
                break

    print(_colored("\nSession closed.", _DIM))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Interactive Factory Droid session with full activity rendering",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="Working directory for the droid session (default: current directory)",
    )
    parser.add_argument(
        "--exec-path",
        default="droid",
        help="Path to the droid executable (default: 'droid')",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main(cwd=args.cwd, exec_path=args.exec_path))
    except KeyboardInterrupt:
        sys.exit(0)
