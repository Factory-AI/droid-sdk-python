"""Authenticated local SDK MCP tool configuration."""

from __future__ import annotations

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


async def main() -> None:
    server = create_sdk_mcp_server("example-tools", [lookup_owner])
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
    asyncio.run(main())
