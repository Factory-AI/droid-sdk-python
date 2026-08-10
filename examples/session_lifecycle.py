#!/usr/bin/env python3
"""Fork a session, load the fork, and continue it.

Usage:
    uv run python examples/session_lifecycle.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from _helpers import run_turn

from droid_sdk import DroidClient


async def main() -> None:
    cwd = str(Path.cwd())

    async with DroidClient(exec_path="droid", cwd=cwd) as client:
        result = await client.initialize_session(
            machine_id="python-sdk-example",
            cwd=cwd,
        )
        print(f"Source session: {result.session_id}")

        await run_turn(client, "Remember the value ORANGE.")
        fork = await client.fork_session(title="Python SDK fork example")
        print(f"Forked session: {fork.new_session_id}")

        await client.load_session(session_id=fork.new_session_id)
        await run_turn(client, "What value did I ask you to remember?")


if __name__ == "__main__":
    asyncio.run(main())
