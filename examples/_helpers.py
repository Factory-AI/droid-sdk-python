"""Shared helpers for the runnable examples."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from droid_sdk import (
    AssistantTextDelta,
    DroidClient,
    ErrorEvent,
    ThinkingTextDelta,
    TokenUsageUpdate,
    ToolProgress,
    ToolResult,
    ToolUse,
    TurnComplete,
)
from droid_sdk.schemas import Base64ImageSource, DocumentSource

ImageInput = Base64ImageSource | dict[str, Any]
DocumentInput = DocumentSource | dict[str, Any]


async def run_turn(
    client: DroidClient,
    prompt: str,
    *,
    images: list[ImageInput] | None = None,
    files: list[DocumentInput] | None = None,
    output_format: dict[str, Any] | None = None,
    show_activity: bool = False,
    collect_text: bool = False,
) -> str | None:
    """Send one prompt, print its stream, and optionally return its text."""

    async def consume() -> str | None:
        chunks: list[str] = []
        error_message: str | None = None

        async for event in client.receive_response():
            if isinstance(event, AssistantTextDelta):
                print(event.text, end="", flush=True)
                if collect_text:
                    chunks.append(event.text)
            elif show_activity and isinstance(event, ThinkingTextDelta):
                print(event.text, end="", flush=True)
            elif show_activity and isinstance(event, ToolUse):
                print(f"\n[tool] {event.tool_name}")
            elif show_activity and isinstance(event, ToolProgress):
                print(f"\n[progress] {event.tool_name}: {event.content}")
            elif show_activity and isinstance(event, ToolResult):
                status = "error" if event.is_error else "done"
                print(f"\n[{status}] {event.tool_name or event.tool_use_id}")
            elif show_activity and isinstance(event, TokenUsageUpdate):
                print(
                    f"\n[tokens] input={event.input_tokens} "
                    f"output={event.output_tokens}"
                )
            elif isinstance(event, ErrorEvent):
                error_message = event.message
            elif isinstance(event, TurnComplete):
                print()
                if error_message is not None:
                    raise RuntimeError(error_message)
                return "".join(chunks) if collect_text else None

        raise RuntimeError("Droid stopped before the turn completed.")

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    try:
        await client.add_user_message(
            text=prompt,
            images=images,
            files=files,
            output_format=output_format,
        )
        return await consumer
    finally:
        if not consumer.done():
            consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer
