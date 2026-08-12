"""One bounded turn with automatic cleanup."""

from __future__ import annotations

import asyncio

from droid_sdk import run


async def main() -> None:
    result = await run("Reply with exactly: SDK ready", timeout=60)
    print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
