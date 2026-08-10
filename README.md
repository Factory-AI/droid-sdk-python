# Factory Droid SDK for Python

Run Factory Droid from Python through a local `droid exec` subprocess. The SDK
uses `asyncio` and streams typed events over JSON-RPC 2.0.

## Choose an API

| Goal | API |
| --- | --- |
| Run one prompt | `query()` |
| Keep context across prompts | `DroidClient` |
| Resume a saved session | `DroidClient.load_session()` |
| Control models, tools, inputs, or lifecycle | `DroidClient` |

`query()` owns one client subprocess and closes it after the turn. Use
`DroidClient` for everything else.

## Install and authenticate

Requirements:

- Python 3.10+
- `droid` on `PATH`

Install the package:

```bash
pip install droid-sdk
```

Or use [uv](https://docs.astral.sh/uv/):

```bash
uv add droid-sdk
```

Set a Factory API key before starting Python:

```bash
export FACTORY_API_KEY="your-key"
```

The `droid` subprocess inherits the Python process environment. You can also
use an existing authenticated Droid CLI installation. Do not commit API keys or
pass them in command-line arguments.

## Quick start

```python
import asyncio

from droid_sdk import AssistantTextDelta, ErrorEvent, query


async def main() -> None:
    error: str | None = None
    async for event in query(
        "Summarize this repository.",
        cwd=".",
        model_id="auto",
    ):
        if isinstance(event, AssistantTextDelta):
            print(event.text, end="", flush=True)
        elif isinstance(event, ErrorEvent):
            error = event.message
    print()
    if error is not None:
        raise RuntimeError(error)


asyncio.run(main())
```

`query()` yields text, thinking, tool, state, token, error, and completion
events. It does not return a final result object.

Runnable example: [`examples/query.py`](examples/query.py)

## Sessions

Use one client for one active session.

```python
import asyncio
import contextlib
from pathlib import Path

from droid_sdk import AssistantTextDelta, DroidClient, ErrorEvent


async def receive(client: DroidClient) -> None:
    error: str | None = None
    async for event in client.receive_response():
        if isinstance(event, AssistantTextDelta):
            print(event.text, end="", flush=True)
        elif isinstance(event, ErrorEvent):
            error = event.message
    print()
    if error is not None:
        raise RuntimeError(error)


async def send(client: DroidClient, prompt: str) -> None:
    response = asyncio.create_task(receive(client))
    await asyncio.sleep(0)
    try:
        await client.add_user_message(text=prompt)
        await response
    finally:
        if not response.done():
            response.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await response


async def main() -> None:
    cwd = str(Path.cwd())
    async with DroidClient(exec_path="droid", cwd=cwd) as client:
        result = await client.initialize_session(
            machine_id="my-app",
            cwd=cwd,
            model_id="auto",
        )
        print(result.session_id)

        await send(client, "What does this repository do?")
        await send(client, "What should I test first?")


asyncio.run(main())
```

The second turn includes context from the first. The context manager connects
the client and always closes its subprocess.

Runnable example:
[`examples/multi_turn_session.py`](examples/multi_turn_session.py)

### Resume a session

```python
async with DroidClient(exec_path="droid") as client:
    result = await client.load_session(session_id="session-id")
    print(result.settings.model_id)
    await send(client, "Continue the previous task.")
```

`load_session()` restores the saved conversation, working directory, and
settings. It raises `SessionNotFoundError` when the ID does not exist.

Runnable example:
[`examples/resume_session.py`](examples/resume_session.py)

### Update settings

```python
from droid_sdk.schemas import AutonomyLevel, ReasoningEffort

await client.update_session_settings(
    model_id="auto",
    reasoning_effort=ReasoningEffort.High,
    autonomy_level=AutonomyLevel.Low,
)
```

Updates apply to later turns in the active session.

### Session lifecycle

```python
await client.rename_session(title="Authentication review")

fork = await client.fork_session(title="Alternative approach")
await client.load_session(session_id=fork.new_session_id)

compacted = await client.compact_session()
await client.load_session(session_id=compacted.new_session_id)
```

`fork_session()`, `compact_session()`, and `execute_rewind()` return a new
session ID. They do not switch the client to that session. Call
`load_session()` to continue the new session.

Runnable example:
[`examples/session_lifecycle.py`](examples/session_lifecycle.py)

## Models

Model IDs depend on the account and organization policy. Omit `model_id` to use
the Droid default.

### Discover models

`initialize_session()` and `load_session()` return `available_models` when the
CLI provides a model catalog:

```python
result = await client.initialize_session(machine_id="my-app", cwd=".")

for model in result.available_models or []:
    print(model.id, model.supported_reasoning_efforts)
```

The server may add fields that are not yet typed. Read them from
`model.model_extra`. Check `disabled` before presenting a model as selectable,
and use `disabledReason` when it is present.

Runnable example:
[`examples/model_discovery.py`](examples/model_discovery.py)

### Select a model

```python
from droid_sdk.schemas import ReasoningEffort

result = await client.initialize_session(
    machine_id="my-app",
    cwd=".",
    model_id="model-id",
    reasoning_effort=ReasoningEffort.High,
)
```

Use a reasoning effort listed in the model's
`supported_reasoning_efforts`. Otherwise, omit it to use the model default.

Runnable example:
[`examples/model_selection.py`](examples/model_selection.py)

### Auto Router

Set `model_id="auto"` to let Factory choose the model:

```python
async for event in query("Find the failing test.", model_id="auto"):
    ...
```

The selected model can change between turns. Use a fixed model ID when every
turn must use the same model.

### Spec mode model

```python
from droid_sdk.schemas import DroidInteractionMode, ReasoningEffort

result = await client.initialize_session(
    machine_id="my-app",
    cwd=".",
    interaction_mode=DroidInteractionMode.Spec,
    spec_mode_model_id="model-id",
    spec_mode_reasoning_effort=ReasoningEffort.High,
)
```

Use `update_session_settings()` to change interaction mode or spec-mode model
settings later. The Python SDK does not yet provide `enter_spec_mode()` or
`exit_spec_mode()` helpers.

### Custom models

Configure custom models in Droid, then pass the configured ID as `model_id`.
Custom IDs use `custom:<model>`. See
[Custom Models (BYOK)](https://docs.factory.ai/cli/byok/overview).

## Streaming and errors

`receive_response()` yields:

| Event | Meaning |
| --- | --- |
| `AssistantTextDelta` | Assistant text |
| `ThinkingTextDelta` | Reasoning text |
| `ToolUse` | Tool call |
| `ToolProgress` | Tool progress |
| `ToolResult` | Tool result |
| `WorkingStateChanged` | Agent state |
| `TokenUsageUpdate` | Cumulative session usage |
| `ErrorEvent` | Turn error |
| `TurnComplete` | Turn finished |

Use `isinstance()` to narrow events:

```python
from droid_sdk import AssistantTextDelta, ErrorEvent, TurnComplete

error: str | None = None
async for event in client.receive_response():
    if isinstance(event, AssistantTextDelta):
        print(event.text, end="", flush=True)
    elif isinstance(event, ErrorEvent):
        error = event.message
    elif isinstance(event, TurnComplete) and event.token_usage:
        print(event.token_usage.input_tokens)

if error is not None:
    raise RuntimeError(error)
```

An `ErrorEvent` reports a problem during the turn. SDK setup, transport, and
protocol failures raise exceptions:

```python
from droid_sdk import (
    ConnectionError as DroidConnectionError,
    DroidClientError,
    ProcessExitError,
    ProtocolError,
    SessionNotFoundError,
    TimeoutError,
)
```

All SDK exceptions inherit from `DroidClientError`.

### Stop a turn

Call `interrupt_session()` from another task:

```python
async def consume_response() -> None:
    async for _ in client.receive_response():
        pass


consumer = asyncio.create_task(consume_response())
await asyncio.sleep(0)
try:
    await client.add_user_message(text="Perform a long review.")
    await client.interrupt_session()
    await consumer
finally:
    if not consumer.done():
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer
```

Breaking out of `receive_response()` only stops the local iterator. It does not
interrupt Droid. Call `interrupt_session()` first when work should stop.

`query()` is an async generator. If you stop it early, close it explicitly:

```python
stream = query("Inspect the repository.")
try:
    async for event in stream:
        break
finally:
    await stream.aclose()
```

## Inputs and structured output

Inputs are available through `DroidClient.add_user_message()`.

### Images and documents

```python
await client.add_user_message(
    text="Summarize the attachments.",
    images=[
        {
            "type": "base64",
            "data": base64_png,
            "mediaType": "image/png",
        }
    ],
    files=[
        {
            "type": "text",
            "mediaType": "text/plain",
            "data": report,
            "name": "report.txt",
        }
    ],
)
```

Supported image types are JPEG, PNG, GIF, and WebP. PDF data must be
base64-encoded with `mediaType` set to `application/pdf`.

Runnable example:
[`examples/attachment.py`](examples/attachment.py)

### Structured output

```python
await client.add_user_message(
    text="Return the repository name.",
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
)
```

The response still arrives as streamed text. Collect the text, then parse it
with `json.loads()`.

Runnable example:
[`examples/structured_output.py`](examples/structured_output.py)

## Permissions and user input

Without handlers, the SDK rejects permission requests and declines AskUser
questions.

### Permission handler

```python
from typing import Any

from droid_sdk import ToolConfirmationOutcome


def handle_permission(params: dict[str, Any]) -> str:
    offered = {option["value"] for option in params["options"]}
    desired = ToolConfirmationOutcome.ProceedOnce.value
    if desired in offered:
        return desired
    cancel = ToolConfirmationOutcome.Cancel.value
    if cancel in offered:
        return cancel
    raise ValueError("No supported permission outcome was offered.")


client.set_permission_handler(handle_permission)
```

Return only an outcome present in `params["options"]`. Handlers may be
synchronous or asynchronous.

Runnable example:
[`examples/permission_handler.py`](examples/permission_handler.py)

### AskUser handler

```python
def handle_ask_user(params: dict[str, Any]) -> dict[str, Any]:
    answers = [
        {
            "index": question["index"],
            "question": question["question"],
            "answer": (question["options"] or ["none"])[0],
        }
        for question in params["questions"]
    ]
    return {"cancelled": False, "answers": answers}


client.set_ask_user_handler(handle_ask_user)
```

To decline, return `{"cancelled": True, "answers": []}`.

## Tools, skills, and MCP

### Control native tools

```python
catalog = await client.list_tools()
tool_ids = [tool.id for tool in catalog.tools]

await client.initialize_session(
    machine_id="my-app",
    cwd=".",
    enabled_tool_ids=[],
    disabled_tool_ids=tool_ids,
)
```

`enabled_tool_ids` is additive. To restrict tools, pass an explicit disable
list. `list_tools()` can run before session initialization.

### List skills

```python
skills = await client.list_skills()
for skill in skills.skills:
    print(skill.name, skill.enabled)
```

The Python SDK can list skills but cannot enable or disable them.

### External MCP servers

Pass MCP server configuration to `initialize_session()` or `load_session()`.
After initialization, use:

- `add_mcp_server()` and `remove_mcp_server()`
- `toggle_mcp_server()` and `toggle_mcp_tool()`
- `list_mcp_servers()`, `list_mcp_tools()`, and `list_mcp_registry()`
- `authenticate_mcp_server()`, `submit_mcp_auth_code()`,
  `cancel_mcp_auth()`, and `clear_mcp_auth()`

The Python SDK does not yet provide in-process SDK MCP tools.

## API reference

### Top-level imports

`droid_sdk` exports the main client, transport, query API, stream events, and
errors. Protocol models and enums are under `droid_sdk.schemas`.

### `DroidClient`

| Method | Purpose |
| --- | --- |
| `initialize_session()` | Create a session |
| `load_session()` | Resume a saved session |
| `add_user_message()` | Start a turn |
| `receive_response()` | Stream the turn |
| `interrupt_session()` | Stop active work |
| `update_session_settings()` | Change active-session settings |
| `list_tools()` / `list_commands()` | Discover tools and commands |
| `get_context_stats()` / `get_context_breakdown()` | Inspect context usage |
| `rename_session()` | Rename the active session |
| `fork_session()` | Fork the active session |
| `compact_session()` | Compact into a new session |
| `get_rewind_info()` / `execute_rewind()` | Inspect and perform rewind |
| `close_session()` | End the active session |
| `list_skills()` | List skills |
| `on_notification()` | Subscribe to raw notifications |
| `set_permission_handler()` | Handle tool approvals |
| `set_ask_user_handler()` | Handle AskUser questions |
| `connect()` / `close()` | Manage the subprocess connection |

### TypeScript SDK differences

The Python SDK currently exposes the subprocess JSON-RPC client. It does not
yet expose the TypeScript SDK's:

- daemon or browser client
- local session listing
- final `DroidResult` object
- in-process SDK MCP tools
- hook stream events
- observability sinks
- Factory REST helpers

## Development

```bash
uv sync
uv run --group dev python -m pytest
uv run mypy --strict src/ examples/
uv run ruff check src/ tests/ examples/
uv run ruff format --check src/ tests/ examples/
```

Live tests create real sessions and consume model usage:

```bash
DROID_LIVE_TESTS=1 uv run --group dev python -m pytest \
  tests/test_live_droid_exec.py -v
```

## License

Apache 2.0. See [LICENSE](LICENSE).
