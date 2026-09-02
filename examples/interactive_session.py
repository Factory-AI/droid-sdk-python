"""Multi-turn complete and partial streaming with public v5 APIs."""

from __future__ import annotations

import asyncio

from droid_sdk import AssistantMessage, Session, TextDelta


async def main() -> None:
    async with Session() as session:
        async with session.stream(
            "Reply with one short sentence.", timeout=60
        ) as first:
            async for event in first:
                if isinstance(event, AssistantMessage):
                    print(event.text)

        async with session.stream(
            "Reply with three words.",
            include_partial_messages=True,
            timeout=60,
        ) as second:
            async for partial_event in second:
                if isinstance(partial_event, TextDelta):
                    print(partial_event.text, end="", flush=True)
        print()


if __name__ == "__main__":
    asyncio.run(main())
