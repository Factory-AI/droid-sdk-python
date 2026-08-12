"""Multi-turn complete and partial streaming with public v5 APIs."""

from __future__ import annotations

import argparse
import asyncio

from droid_sdk import AssistantMessage, Session, TextDelta


async def main(run_turns: bool = False) -> None:
    if not run_turns:
        session = Session()
        assert session.cwd is not None
        print("self-test: lazy session configured")
        return

    async with Session() as session:
        async with session.stream(
            "Reply with one short sentence.", timeout=60
        ) as first:
            async for event in first:
                if isinstance(event, AssistantMessage):
                    print(event.text)
        assert first.result.session_id == session.id

        async with session.stream(
            "Reply with three words.",
            include_partial_messages=True,
            timeout=60,
        ) as second:
            async for event in second:
                if isinstance(event, TextDelta):
                    print(event.text, end="", flush=True)
        print()
        assert second.result.turn_count == 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    asyncio.run(main(parser.parse_args().run))
