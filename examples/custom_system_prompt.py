"""Append session-specific instructions to Droid's built-in prompt."""

from __future__ import annotations

import asyncio

from droid_sdk import DroidSystemPrompt, SessionConfig, run


async def main() -> None:
    result = await run(
        "Summarize the main entry points in this project.",
        config=SessionConfig(
            system_prompt=DroidSystemPrompt(
                append="Keep answers concise and cite relevant files."
            )
        ),
        timeout=60,
    )
    print(result.text if result.success else result.subtype)


if __name__ == "__main__":
    asyncio.run(main())
