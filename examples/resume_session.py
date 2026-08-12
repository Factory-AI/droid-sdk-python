"""Resume a persisted session by ID."""

from __future__ import annotations

import argparse
import asyncio

from droid_sdk import Session


async def main(session_id: str | None) -> None:
    if session_id is None:
        print("self-test: pass --session-id to resume")
        return
    async with Session.resume(session_id) as session:
        async with session.stream("Reply with: resumed", timeout=60) as stream:
            async for _ in stream:
                pass
        print(stream.result.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id")
    asyncio.run(main(parser.parse_args().session_id))
