#!/usr/bin/env python3
"""Run a prompt with Auto Router or a fixed model.

Usage:
    uv run python examples/model_selection.py
    uv run python examples/model_selection.py --model MODEL_ID
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from _helpers import run_turn

from droid_sdk import DroidClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="auto",
        help="Model ID returned by model_discovery.py (default: auto)",
    )
    return parser.parse_args()


async def main(model_id: str) -> None:
    cwd = str(Path.cwd())

    async with DroidClient(exec_path="droid", cwd=cwd) as client:
        result = await client.initialize_session(
            machine_id="python-sdk-example",
            cwd=cwd,
            model_id=model_id,
        )
        print(f"Configured model: {result.settings.model_id}")
        await run_turn(client, "Find the main entry point in this repository.")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.model))
