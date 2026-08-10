#!/usr/bin/env python3
"""Approve one offered tool request at a time.

Usage:
    uv run python examples/permission_handler.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from _helpers import run_turn

from droid_sdk import DroidClient, ToolConfirmationOutcome
from droid_sdk.schemas import AutonomyLevel


def handle_permission(params: dict[str, Any]) -> str:
    offered = {option.get("value") for option in params.get("options", [])}
    desired = ToolConfirmationOutcome.ProceedOnce.value
    if desired in offered:
        return desired
    cancel = ToolConfirmationOutcome.Cancel.value
    if cancel in offered:
        return cancel
    raise ValueError("No supported permission outcome was offered.")


async def main() -> None:
    cwd = str(Path.cwd())

    async with DroidClient(exec_path="droid", cwd=cwd) as client:
        client.set_permission_handler(handle_permission)
        await client.initialize_session(
            machine_id="python-sdk-example",
            cwd=cwd,
            autonomy_level=AutonomyLevel.Off,
        )
        await run_turn(
            client,
            "List the top-level files. Do not modify anything.",
            show_activity=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
