#!/usr/bin/env python3
"""Run an interactive Droid session.

Usage:
    uv run python examples/interactive_session.py [--cwd PATH] [--model MODEL_ID]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from pathlib import Path
from typing import Any

from _helpers import run_turn

from droid_sdk import DroidClient, ToolConfirmationOutcome


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--model")
    parser.add_argument("--exec-path", default="droid")
    return parser.parse_args()


async def ask(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def handle_permission(params: dict[str, Any]) -> str:
    offered = {
        option.get("value"): option.get("label", option.get("value"))
        for option in params.get("options", [])
    }
    tool_names = [
        item.get("toolUse", {}).get("name", "unknown")
        for item in params.get("toolUses", [])
    ]
    answer = (await ask(f"Allow {', '.join(tool_names)} once? [y/N] ")).lower()
    desired = ToolConfirmationOutcome.ProceedOnce.value
    if answer == "y" and desired in offered:
        return desired
    cancel = ToolConfirmationOutcome.Cancel.value
    if cancel in offered:
        return cancel
    raise ValueError("No supported permission outcome was offered.")


async def handle_ask_user(params: dict[str, Any]) -> dict[str, Any]:
    answers = []
    for question in params.get("questions", []):
        options = ", ".join(question.get("options", []))
        answer = await ask(f"{question['question']} [{options}] ")
        answers.append(
            {
                "index": question["index"],
                "question": question["question"],
                "answer": answer,
            }
        )
    return {"cancelled": False, "answers": answers}


async def main(cwd: Path, model_id: str | None, exec_path: str) -> None:
    resolved_cwd = str(cwd.resolve())

    async with DroidClient(exec_path=exec_path, cwd=resolved_cwd) as client:
        client.set_permission_handler(handle_permission)
        client.set_ask_user_handler(handle_ask_user)

        result = await client.initialize_session(
            machine_id="python-sdk-interactive-example",
            cwd=resolved_cwd,
            model_id=model_id,
        )
        print(f"Session: {result.session_id}")
        print("Enter a prompt. Type exit to stop.")

        while True:
            prompt = (await ask("> ")).strip()
            if prompt.lower() in {"exit", "quit"}:
                return
            if prompt:
                await run_turn(client, prompt, show_activity=True)


if __name__ == "__main__":
    args = parse_args()
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        asyncio.run(main(args.cwd, args.model, args.exec_path))
