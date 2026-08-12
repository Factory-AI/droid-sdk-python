# Factory Droid SDK for Python

Async Python 3.10+ SDK for local Factory Droid sessions.

## Install and authenticate

```bash
pip install droid-sdk
```

Use an authenticated local Droid CLI session, or set `FACTORY_API_KEY`.

The `droid` executable must be on `PATH`. Keys are passed through the child
process environment, never command arguments.

## One turn or a conversation

Use `run()` for one turn:

```python
import asyncio
from droid_sdk import run

async def main() -> None:
    result = await run("Summarize this repository.", timeout=60)
    print(result.text if result.success else result.subtype)

asyncio.run(main())
```

Use `Session` for shared history and operations:

```python
import asyncio

from droid_sdk import AssistantMessage, Session

async def main() -> None:
    async with Session() as session:
        async with session.stream("What does this project do?") as stream:
            async for event in stream:
                if isinstance(event, AssistantMessage):
                    print(event.text)
        print(stream.result.subtype, session.id)

asyncio.run(main())
```

Sessions are lazy. `async with` opens and closes them. A manually opened
session must be closed by its caller. A session permits one active stream;
different sessions can run concurrently. Breaking iteration inside the stream
context, timeout, or task cancellation performs a best-effort interrupt and
detaches subscriptions. `run()` always closes everything it creates.

## Results, errors, and typing

Terminal outcomes are immutable `RunSuccess`, `RunInterrupted`, or
`RunFailure` values. Execution, interruption, and structured-output failures
do not raise. Setup, connection, process, protocol, timeout, and cancellation
failures do. `asyncio.CancelledError` is never wrapped.

The wheel contains `py.typed`. Result and event unions narrow with
`isinstance()`. `stream.result` is cached after completion and raises
`StreamIncompleteError` before then.

## Structured output and attachments

```python
import asyncio

from pydantic import BaseModel
from droid_sdk import Document, Image, run

class Summary(BaseModel):
    title: str
    risks: list[str]

async def main() -> None:
    result = await run(
        "Summarize these inputs.",
        output=Summary,
        images=[Image.from_path("screen.png")],
        files=[Document.from_text("notes", name="notes.txt")],
    )
    if result.output is not None:
        print(result.output.title)

asyncio.run(main())
```

`JsonSchema` provides raw object-shaped JSON Schema output. Local constructors
support PNG/JPEG/GIF/WebP images, text documents, and PDFs. Invalid inputs
raise `InvalidAttachmentError` before a turn starts.

## Interactions and controls

Attach `InteractionHandlers(on_permission=..., on_question=...)`. Permission
responses must choose an option offered by Droid; invalid responses and
handler failures safely cancel. Typed action classes are available from
`droid_sdk.permissions`.

`SessionConfig` and `update_settings()` support model, reasoning, mode,
autonomy, tags, and all four native-tool controls:

- `additional_tools`: add catalog IDs
- `enabled_tools`: enable available IDs
- `disabled_tools`: subtract IDs
- `restrict_tools`: restrictive allowlist; it never elevates permission

Use `list_tools()`, `list_skills()`, MCP operations, `context()`,
`enter_spec()`/`leave_spec()`, `rename()`, and raw filtered
`on_notification()` subscriptions for ongoing sessions.

## Resume and replacement ownership

```python
async with Session.resume(saved_id) as session:
    ...
```

Resume restores persisted history, cwd, title, and settings; handlers, runtime,
tool policy, observability, and session-scoped MCP servers must be attached
again.

`fork()`, `compact()`, and `rewind()` return an already-open successor that
owns the existing connection. The source is retired: identity remains
readable, active methods raise `SessionReplacedError`, and source `close()` is
a no-op.

## MCP and custom runtime

External stdio, HTTP, and SSE configs live in `droid_sdk.mcp`. Annotated
Python functions can be exposed through an authenticated loopback-only
Streamable HTTP server:

```python
from droid_sdk import SessionConfig
from droid_sdk.mcp import create_sdk_mcp_server, tool

@tool("lookup", "Look up a local value.")
def lookup(key: str) -> str:
    return f"value:{key}"

server = create_sdk_mcp_server("local-tools", [lookup])
config = SessionConfig(mcp_servers=[server])
```

The session starts and stops SDK MCP servers. Every start uses an ephemeral
port and fresh bearer token.

`Runtime` configures executable, extra args, environment, transport, and
privacy-safe observability. A caller transport must already be connected,
takes precedence over process options, and is closed by the session.

## Saved sessions and examples

`await list_sessions()` reads local session files without starting Droid.
Use `all_workspaces=True`, `cwd=`, or `limit=`.

Runnable examples are under `examples/`; offline examples require no
credentials, while model examples use bounded prompts and finite timeouts.
The complete command matrix is in
[`docs/python-sdk-reference.md`](docs/python-sdk-reference.md#runnable-examples).
See the complete contract in
[`docs/python-sdk-reference.md`](docs/python-sdk-reference.md).

## Low-level escape hatch

Applications that own JSON-RPC lifecycle can import `DroidClient`,
`ProcessTransport`, transport protocols, and wire schemas from
`droid_sdk.low_level`. Legacy query/client/transport/event aliases are not
exported at package root. Mission and daemon APIs are excluded from the
package root; Mission wire schemas remain available through
`droid_sdk.low_level`.

## Limitations

- Local `droid` subprocesses only
- asyncio only
- one active turn per session
- hooks remain file-configured
- image URLs are unsupported

Apache-2.0. See [LICENSE](LICENSE).
