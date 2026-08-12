"""One bounded turn with automatic cleanup."""

from __future__ import annotations

import argparse
import asyncio

from droid_sdk import run


async def main(run_turn: bool = False) -> None:
    if not run_turn:
        print("self-test: import and event loop ready")
        return
    result = await run("Reply with exactly: SDK ready", timeout=60)
    print(result.text)
    assert result.session_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    asyncio.run(main(parser.parse_args().run))
