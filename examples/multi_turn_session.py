#!/usr/bin/env python3
"""Run two prompts in the same session.

Usage:
    uv run python examples/multi_turn_session.py
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
            model_id="auto",
        )
        print(f"Session: {result.session_id}")

        await run_turn(client, "What does this repository do?")
        await run_turn(client, "What should I test first?")


if __name__ == "__main__":
    asyncio.run(main())
