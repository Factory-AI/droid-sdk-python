#!/usr/bin/env python3
"""Resume a saved session.

Usage:
    uv run python examples/resume_session.py SESSION_ID
"""

from __future__ import annotations

import argparse
import asyncio

from _helpers import run_turn

from droid_sdk import DroidClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    return parser.parse_args()


async def main(session_id: str) -> None:
    async with DroidClient(exec_path="droid") as client:
        result = await client.load_session(session_id=session_id)
        print(f"Model: {result.settings.model_id}")
        await run_turn(client, "Continue from the previous conversation.")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.session_id))
