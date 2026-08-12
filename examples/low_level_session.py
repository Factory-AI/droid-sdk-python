"""Initialize a local Droid session and list its available tools."""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
from pathlib import Path

from droid_sdk.low_level import DroidClient, ListToolsResult


async def run_session(
    client: DroidClient,
    *,
    cwd: str,
    machine_id: str,
) -> ListToolsResult:
    """Run the example flow with a caller-provided low-level client."""
    await client.connect()
    try:
        initialized = await client.initialize_session(
            machine_id=machine_id,
            cwd=cwd,
        )
        tools = await client.list_tools()
        print(f"Session: {initialized.session_id}")
        print(f"Available tools: {len(tools.tools)}")
        return tools
    finally:
        await client.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--droid", default="droid", help="Path to the Droid CLI")
    parser.add_argument("--cwd", default=os.getcwd(), help="Session working directory")
    args = parser.parse_args()

    cwd = str(Path(args.cwd).resolve())
    client = DroidClient(exec_path=args.droid, cwd=cwd)
    await run_session(client, cwd=cwd, machine_id=socket.gethostname())


if __name__ == "__main__":
    asyncio.run(main())
