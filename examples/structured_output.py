#!/usr/bin/env python3
"""Request and parse JSON that follows a JSON Schema.

Usage:
    uv run python examples/structured_output.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from _helpers import run_turn

from droid_sdk import DroidClient


async def main() -> None:
    cwd = str(Path.cwd())
    output_format: dict[str, Any] = {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["name", "language"],
            "additionalProperties": False,
        },
    }

    async with DroidClient(exec_path="droid", cwd=cwd) as client:
        await client.initialize_session(
            machine_id="python-sdk-example",
            cwd=cwd,
            model_id="auto",
        )
        text = await run_turn(
            client,
            "Return this repository's name and primary language.",
            output_format=output_format,
            collect_text=True,
        )

    if text is None:
        raise RuntimeError("No structured output was returned.")
    value = json.loads(text)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
