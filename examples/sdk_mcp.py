"""Authenticated local SDK MCP tool configuration."""

from __future__ import annotations

import argparse
import asyncio

from droid_sdk import (
    InteractionHandlers,
    PermissionRequest,
    PermissionResponse,
    Session,
    SessionConfig,
    ToolConfirmationOutcome,
)
from droid_sdk.mcp import ToolResponse, create_sdk_mcp_server, tool


@tool("lookup_owner", "Return a deterministic file owner.")
def lookup_owner(path: str) -> ToolResponse:
    return ToolResponse(
        content=f"Owner for {path}: platform-team",
        structured_content={"owner": "platform-team"},
    )


def allow_example_tool(request: PermissionRequest) -> PermissionResponse:
    return request.respond(ToolConfirmationOutcome.PROCEED_ONCE)


async def main(run_turn: bool = False) -> None:
    server = create_sdk_mcp_server("example-tools", [lookup_owner])
    if not run_turn:
        config = await server.start()
        assert config.url.startswith("http://127.0.0.1:")
        await server.close()
        assert server.config is None
        print("self-test: MCP started and stopped")
        return
    async with Session(
        config=SessionConfig(mcp_servers=[server]),
        interactions=InteractionHandlers(on_permission=allow_example_tool),
    ) as session:
        async with session.stream(
            "Use lookup_owner for README.md and report its answer.",
            timeout=60,
        ) as stream:
            async for _ in stream:
                pass
        print(stream.result.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    asyncio.run(main(parser.parse_args().run))
