# Factory Droid SDK for Python

A Python asyncio SDK for communicating with the [Factory](https://factory.ai) Droid agent via JSON-RPC 2.0 over a subprocess (`droid exec`).

## Requirements

- Python 3.10+
- `droid` CLI installed (available at `~/.local/bin/droid`)

## Installation

```bash
pip install droid-sdk
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add droid-sdk
```

## Quick Start

The simplest way to use the SDK is with the `query()` convenience function, which handles the full session lifecycle automatically:

```python
import asyncio
from droid_sdk import query, DroidQueryOptions
from droid_sdk.stream import AssistantTextDelta, TurnComplete

async def main():
    async for msg in query("Explain this codebase", cwd="/path/to/project"):
        if isinstance(msg, AssistantTextDelta):
            print(msg.text, end="", flush=True)
        elif isinstance(msg, TurnComplete):
            print("\nDone!")

asyncio.run(main())
```

You can also pass a `DroidQueryOptions` object for more control:

```python
async def main():
    options = DroidQueryOptions(
        cwd="/path/to/project",
        model_id="claude-sonnet-4",
        reasoning_effort=ReasoningEffort.High,
    )
    async for msg in query("Fix the bug in main.py", options=options):
        if isinstance(msg, AssistantTextDelta):
            print(msg.text, end="", flush=True)
```

### Using DroidClient directly

For more control over the session lifecycle, use `DroidClient` directly with `receive_response()`:

```python
import asyncio
from droid_sdk import (
    DroidClient,
    ProcessTransport,
    AssistantTextDelta,
    ThinkingTextDelta,
    ToolUse,
    ToolResult,
    TurnComplete,
)

async def main():
    # Create a transport that spawns a droid exec subprocess
    transport = ProcessTransport(exec_path="droid", cwd="/path/to/project")

    # Use as an async context manager for automatic cleanup
    async with DroidClient(transport=transport) as client:
        # Initialize a new session
        result = await client.initialize_session(
            machine_id="my-machine",
            cwd="/path/to/project",
        )
        print(f"Session ID: {result.session_id}")

        # Send a message and stream the response
        await client.add_user_message(text="Hello, Droid!")

        async for msg in client.receive_response():
            if isinstance(msg, AssistantTextDelta):
                print(msg.text, end="", flush=True)
            elif isinstance(msg, ThinkingTextDelta):
                print(f"[thinking] {msg.text}")
            elif isinstance(msg, ToolUse):
                print(f"\n🔧 Using tool: {msg.tool_name}")
            elif isinstance(msg, ToolResult):
                print(f"   Result: {msg.content}")
            elif isinstance(msg, TurnComplete):
                if msg.token_usage:
                    print(f"\nTokens: {msg.token_usage.input_tokens} in / {msg.token_usage.output_tokens} out")
                print("Done!")

    # Transport and subprocess are cleaned up automatically

asyncio.run(main())
```

## Event Handling

Register listeners for real-time notifications from the droid process:

```python
from droid_sdk import (
    DroidClient,
    ProcessTransport,
    SessionNotificationType,
)

async def main():
    transport = ProcessTransport(exec_path="droid", cwd="/path/to/project")
    async with DroidClient(transport=transport) as client:
        # Listen for all notifications
        def on_notification(notification):
            params = notification.get("params", {})
            inner = params.get("notification", {})
            print(f"Notification type: {inner.get('type')}")

        client.on_notification(on_notification)

        # Or filter by notification type
        def on_text_delta(notification):
            params = notification["params"]["notification"]
            print(params.get("textDelta", ""), end="", flush=True)

        client.on_notification(
            on_text_delta,
            notification_type=SessionNotificationType.ASSISTANT_TEXT_DELTA,
        )

        result = await client.initialize_session(
            machine_id="my-machine",
            cwd="/path/to/project",
        )
        await client.add_user_message(text="Explain this codebase")

        # Keep running to receive streamed notifications
        import asyncio
        await asyncio.sleep(60)
```

## Stream Type Checking

All stream message types are simple dataclasses that can be used with `isinstance()` for type-safe message handling:

```python
from droid_sdk import (
    AssistantTextDelta,
    ThinkingTextDelta,
    ToolUse,
    ToolResult,
    ToolProgress,
    WorkingStateChanged,
    TokenUsageUpdate,
    TurnComplete,
    ErrorEvent,
    StreamMessage,
)

def handle_message(msg: StreamMessage) -> None:
    """Handle a stream message with exhaustive type checking."""
    if isinstance(msg, AssistantTextDelta):
        print(msg.text, end="", flush=True)
    elif isinstance(msg, ThinkingTextDelta):
        print(f"[thinking] {msg.text}")
    elif isinstance(msg, ToolUse):
        print(f"Tool call: {msg.tool_name}({msg.tool_input})")
    elif isinstance(msg, ToolResult):
        status = "❌" if msg.is_error else "✅"
        # tool_use_id correlates the result with its ToolUse; tool_name is
        # backfilled from that call (None if the call was never seen).
        print(f"{status} [{msg.tool_use_id}] {msg.tool_name}: {msg.content}")
    elif isinstance(msg, ToolProgress):
        print(f"  ⏳ {msg.tool_name}: {msg.content}")
    elif isinstance(msg, WorkingStateChanged):
        print(f"State: {msg.state.value}")
    elif isinstance(msg, TokenUsageUpdate):
        print(f"Tokens: {msg.input_tokens} in / {msg.output_tokens} out")
    elif isinstance(msg, TurnComplete):
        print("\n--- Turn complete ---")
    elif isinstance(msg, ErrorEvent):
        # error_type is often the unhelpful "Error"; error_name exposes the
        # nested error.name (e.g. "LLMInvalidRequestError") to branch on.
        print(f"Error [{msg.error_name or msg.error_type}]: {msg.message}")
```

## Permission Handler

Handle permission requests when Droid needs approval to execute tools:

```python
from droid_sdk import DroidClient, ProcessTransport, ToolConfirmationOutcome

async def main():
    transport = ProcessTransport(exec_path="droid", cwd="/path/to/project")
    async with DroidClient(transport=transport) as client:

        def handle_permission(params):
            tool_uses = params.get("toolUses", [])
            for tool in tool_uses:
                tool_use = tool.get("toolUse", {})
                print(f"Permission requested for: {tool_use.get('name')}")
            # Approve the action
            return ToolConfirmationOutcome.ProceedOnce.value

        client.set_permission_handler(handle_permission)

        result = await client.initialize_session(
            machine_id="my-machine",
            cwd="/path/to/project",
        )
        await client.add_user_message(text="Create a hello.py file")
```

## Error Handling

The SDK provides a typed error hierarchy:

```python
from droid_sdk import (
    DroidClient,
    DroidClientError,
    ConnectionError,
    TimeoutError,
    ProtocolError,
    SessionError,
    SessionNotFoundError,
    ProcessExitError,
)

async def main():
    # ... setup client ...
    try:
        result = await client.load_session(session_id="nonexistent")
    except SessionNotFoundError as e:
        print(f"Session not found: {e.session_id}")
    except TimeoutError as e:
        print(f"Request timed out after {e.timeout_duration}s")
    except ConnectionError as e:
        print(f"Connection failed: {e}")
    except ProtocolError as e:
        print(f"Protocol error (code={e.code}): {e.message}")
    except DroidClientError as e:
        print(f"SDK error: {e}")
```

**Error hierarchy:**

- `DroidClientError` — base for all SDK errors
  - `ConnectionError` — transport/connection failures
  - `TimeoutError` — request timeout
  - `ProtocolError` — JSON-RPC protocol errors
  - `SessionError` — session-related errors
    - `SessionNotFoundError` — session does not exist
  - `ProcessExitError` — subprocess exited unexpectedly

## API Reference

### `DroidClient`

The main client class. Wraps a transport and provides typed async methods for all `droid.*` RPC methods.

**Session methods:**
- `initialize_session(...)` — Create a new session (supports `enabled_tool_ids` and `disabled_tool_ids`)
- `load_session(session_id=...)` — Load an existing session
- `add_user_message(text=..., output_format=...)` — Send a user message, optionally with a structured-output (JSON Schema) contract
- `interrupt_session()` — Interrupt the current session
- `kill_worker_session(worker_session_id=...)` — Kill a worker session
- `update_session_settings(...)` — Update session settings (supports `enabled_tool_ids`/`disabled_tool_ids`)
- `close_session(reason=...)` — Close the active session
- `compact_session(custom_instructions=...)` — Compact the conversation to reclaim context
- `fork_session(title=..., tags=...)` — Fork the session into a new one
- `rename_session(title=...)` — Rename the session

**Discovery methods:**
- `list_tools(...)` — List native CLI tools with `default_allowed`/`currently_allowed` (useful for locking the tool set down)
- `list_commands()` — List custom slash commands

**Context and rewind methods:**
- `get_context_stats()` — Context-window usage (used/remaining/limit)
- `get_context_breakdown()` — Per-category/skill/MCP/droid token breakdown
- `get_rewind_info(message_id=...)` — Restorable/created/evicted files for a rewind point
- `execute_rewind(...)` — Rewind to a message, forking the session

**Locking the tool set down:**

```python
# enabled_tool_ids is additive, so pass an explicit disable list to
# actually restrict native tools. list_tools() lets you verify the result.
catalog = await client.list_tools()
tool_ids = [t.id for t in catalog.tools]
await client.update_session_settings(enabled_tool_ids=[], disabled_tool_ids=tool_ids)
```

**Structured output:**

```python
await client.add_user_message(
    text="Return an answer.",
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
        },
    },
)
```

**MCP methods:**
- `toggle_mcp_server(...)` — Enable/disable an MCP server
- `authenticate_mcp_server(...)` — Authenticate an MCP server (OAuth)
- `cancel_mcp_auth(...)` / `clear_mcp_auth(...)` — Cancel/clear MCP auth
- `submit_mcp_auth_code(...)` — Submit an MCP auth code
- `add_mcp_server(...)` / `remove_mcp_server(...)` — Add/remove MCP servers
- `list_mcp_registry()` / `list_mcp_tools()` / `list_mcp_servers()` — List MCP resources
- `toggle_mcp_tool(...)` — Enable/disable an MCP tool

**Other methods:**
- `list_skills()` — List available skills
- `submit_bug_report(...)` — Submit a bug report

**Event system:**
- `on_notification(callback, notification_type=None)` — Register a notification listener
- `set_permission_handler(handler)` / `clear_permission_handler()` — Permission handling
- `set_ask_user_handler(handler)` / `clear_ask_user_handler()` — Ask-user handling

**Lifecycle:**
- `connect()` / `close()` — Manual connection management
- `async with DroidClient(...) as client:` — Context manager (recommended)

### `ProcessTransport`

Spawns a `droid exec` subprocess and manages JSONL communication over stdin/stdout.

### `DroidClientTransport`

Protocol (interface) that all transport implementations must satisfy. Use this to create custom transports for testing or alternative communication channels.

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run --group dev python -m pytest

# Run opt-in tests against the installed, authenticated droid exec CLI.
# These create real sessions and consume model usage.
DROID_LIVE_TESTS=1 uv run --group dev python -m pytest \
  tests/test_live_droid_exec.py -v

# Override the executable path when droid is not on PATH.
DROID_LIVE_TESTS=1 DROID_EXEC_PATH=/path/to/droid \
  uv run --group dev python -m pytest tests/test_live_droid_exec.py -v

# Type check (strict mode)
uv run mypy --strict src/

# Lint and format
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
