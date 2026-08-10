#!/usr/bin/env python3
"""List models returned during session initialization.

Usage:
    uv run python examples/model_discovery.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from droid_sdk import DroidClient


async def main() -> None:
    cwd = str(Path.cwd())

    async with DroidClient(exec_path="droid", cwd=cwd) as client:
        result = await client.initialize_session(
            machine_id="python-sdk-example",
            cwd=cwd,
        )

        for model in result.available_models or []:
            extra = model.model_extra or {}
            state = f"disabled: {extra.get('disabledReason', 'unavailable')}"
            if not extra.get("disabled"):
                state = "available"
            efforts = ", ".join(
                effort.value for effort in model.supported_reasoning_efforts
            )
            print(f"{model.id}\t{state}\t{efforts}")


if __name__ == "__main__":
    asyncio.run(main())
