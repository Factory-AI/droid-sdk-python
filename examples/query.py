#!/usr/bin/env python3
"""Run one prompt with query().

Usage:
    uv run python examples/query.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from droid_sdk import AssistantTextDelta, ErrorEvent, query


async def main() -> None:
    error: str | None = None
    async for event in query(
        "Summarize this repository.",
        cwd=str(Path.cwd()),
        model_id="auto",
    ):
        if isinstance(event, AssistantTextDelta):
            print(event.text, end="", flush=True)
        elif isinstance(event, ErrorEvent):
            error = event.message
    print()
    if error is not None:
        raise RuntimeError(error)


if __name__ == "__main__":
    asyncio.run(main())
